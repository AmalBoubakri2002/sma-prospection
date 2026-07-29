import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.scoring.decision import decide_status
from app.agents.veille.sirene import SireneAPIError, SireneClient, SireneConfigError
from app.api.deps import require_active_user
from app.db.base import get_db
from app.models.agent_task import AgentName
from app.models.lead import Lead, LeadStatus
from app.models.user import User
from app.schemas.campaign import (
    AgentTaskSummary,
    CampaignCreate,
    CampaignEstimateResponse,
    CampaignResponse,
    CampaignStatusResponse,
    CampaignStatusUpdate,
    ScoreMinimumUpdate,
)
from app.services.agent_task import create_task, get_latest_active_task
from app.services.campaign import (
    create_campaign,
    delete_campaign,
    get_campaign,
    list_campaigns,
    update_campaign_status,
)
from app.services.lead import (
    count_leads_by_campaign,
    count_leads_by_status_for_campaign,
    count_sirets_in_prospection_matching,
)

router = APIRouter()


@router.post("/", response_model=CampaignResponse, status_code=201)
async def create(
    data: CampaignCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user),
):
    return await create_campaign(db, data, current_user.id)


@router.get("/", response_model=list[CampaignResponse])
async def list_(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user),
):
    campaigns = await list_campaigns(db, current_user.id)
    counts = await count_leads_by_campaign(db, current_user.id)
    for campaign in campaigns:
        campaign.leads_count = counts.get(campaign.id, 0)
    return campaigns


# Déclarée AVANT /{campaign_id}, sinon FastAPI tenterait de parser "estimate"
# comme un UUID de campagne.
@router.get("/estimate", response_model=CampaignEstimateResponse)
async def estimate_pool(
    codes_naf: str,
    codes_postaux: str,
    tranches_effectifs: str = "",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user),
):
    """Estime le vivier disponible pour des critères de ciblage (avant lancement) :
    total SIRENE moins les entreprises déjà en prospection dans d'autres campagnes.
    Les listes sont passées en query string séparées par des virgules."""
    naf = [c.strip() for c in codes_naf.split(",") if c.strip()]
    cps = [c.strip() for c in codes_postaux.split(",") if c.strip()]
    tranches = [c.strip() for c in tranches_effectifs.split(",") if c.strip()]
    if not naf or not cps:
        raise HTTPException(status_code=422, detail="codes_naf et codes_postaux requis")

    try:
        total = await SireneClient().count_etablissements(naf, cps, tranches)
    except SireneConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except SireneAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    en_prospection = await count_sirets_in_prospection_matching(db, naf, cps)
    return CampaignEstimateResponse(
        total_sirene=total,
        deja_en_prospection=en_prospection,
        disponible_estime=max(total - en_prospection, 0),
    )


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user),
):
    campaign = await get_campaign(db, campaign_id, current_user.id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campagne introuvable")
    return campaign


@router.patch("/{campaign_id}/status", response_model=CampaignResponse)
async def update_status(
    campaign_id: uuid.UUID,
    data: CampaignStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user),
):
    campaign = await get_campaign(db, campaign_id, current_user.id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campagne introuvable")
    return await update_campaign_status(db, campaign, data.status)


@router.post("/{campaign_id}/start", response_model=CampaignResponse, status_code=202)
async def start(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user),
):
    campaign = await get_campaign(db, campaign_id, current_user.id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campagne introuvable")
    if campaign.status == "running":
        raise HTTPException(status_code=409, detail="La campagne est déjà en cours")

    # Déclenche le graphe LangGraph complet (pipeline_graph.py).
    # worker_pipeline.py récupère cette tâche et orchestre toutes les étapes.
    # Le payload est conservé à titre d'audit ; le worker relit la campagne depuis la DB.
    await create_task(
        db,
        campaign_id=campaign.id,
        agent_name=AgentName.PIPELINE,
        payload={
            "codes_naf": campaign.codes_naf,
            "codes_postaux": campaign.codes_postaux,
            "tranches_effectifs": campaign.tranches_effectifs,
            "quota": campaign.quota,
        },
    )
    return await update_campaign_status(db, campaign, "running")


@router.post("/{campaign_id}/validate", response_model=CampaignResponse, status_code=202)
async def validate(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user),
):
    """Reprend le pipeline LangGraph après validation commerciale des emails.

    À appeler quand le commercial a terminé de valider / rejeter les leads
    en attente (statut EN_ATTENTE_VALIDATION). Déclenche la reprise du graphe
    depuis le nœud CRM via Command(resume=None) dans worker_pipeline.py.
    """
    campaign = await get_campaign(db, campaign_id, current_user.id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campagne introuvable")
    if campaign.status != "en_attente_validation":
        raise HTTPException(
            status_code=409,
            detail=(
                f"La campagne n'est pas en attente de validation "
                f"(statut actuel : {campaign.status})"
            ),
        )
    await create_task(
        db,
        campaign_id=campaign.id,
        agent_name=AgentName.PIPELINE_RESUME,
        payload={},
    )
    return await update_campaign_status(db, campaign, "crm_pending")


@router.get("/{campaign_id}/status", response_model=CampaignStatusResponse)
async def get_status(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user),
):
    campaign = await get_campaign(db, campaign_id, current_user.id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campagne introuvable")

    # Compteurs par statut en une seule requête SQL
    counts = await count_leads_by_status_for_campaign(db, campaign.id)

    # Tâche agent active (PENDING/RUNNING) ou dernière terminée
    task = await get_latest_active_task(db, campaign.id)
    task_summary = None
    if task:
        task_summary = AgentTaskSummary(
            agent_name=task.agent_name,
            status=task.status,
            attempts=task.attempts,
            error=(task.result or {}).get("error") if task.result else None,
        )

    return CampaignStatusResponse(
        id=campaign.id,
        status=campaign.status,
        leads_collectes=counts.get("COLLECTE", 0),
        leads_enrichis=counts.get("ENRICHI", 0),
        leads_qualifies=counts.get("QUALIFIE", 0),
        leads_ecartes=counts.get("ECARTE", 0),
        leads_email_genere=counts.get("EMAIL_GENERE", 0),
        leads_en_validation=counts.get("EN_ATTENTE_VALIDATION", 0),
        leads_valides=counts.get("VALIDE", 0),
        leads_rejetes=counts.get("REJETE", 0),
        task=task_summary,
    )


@router.post("/{campaign_id}/score", response_model=CampaignResponse, status_code=202)
async def score(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user),
):
    campaign = await get_campaign(db, campaign_id, current_user.id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campagne introuvable")
    if campaign.status in ("running", "scoring_pending"):
        raise HTTPException(status_code=409, detail="Un agent est déjà en cours sur cette campagne")

    await create_task(db, campaign_id=campaign.id, agent_name=AgentName.SCORING, payload={})
    return await update_campaign_status(db, campaign, "scoring_pending")


@router.patch("/{campaign_id}/score-minimum", response_model=CampaignResponse)
async def update_score_minimum(
    campaign_id: uuid.UUID,
    data: ScoreMinimumUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user),
):
    campaign = await get_campaign(db, campaign_id, current_user.id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campagne introuvable")
    campaign.score_minimum = data.score_minimum
    await db.commit()
    await db.refresh(campaign)
    return campaign


@router.post("/{campaign_id}/requalify")
async def requalify(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user),
):
    """Reclasse tous les leads scorés selon le score_minimum actuel de la campagne."""
    campaign = await get_campaign(db, campaign_id, current_user.id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campagne introuvable")

    threshold = campaign.score_minimum

    # Seuls QUALIFIE et ECARTE (rejets automatiques) sont reclassés.
    # Les leads REJETE (rejet humain explicite) ne sont PAS modifiés.
    result = await db.execute(
        select(Lead).where(
            Lead.campaign_id == campaign_id,
            Lead.score.is_not(None),
            Lead.status.in_([LeadStatus.QUALIFIE, LeadStatus.ECARTE]),
        )
    )
    leads = result.scalars().all()

    qualified = rejected = 0
    for lead in leads:
        # Même règle que l'Agent Scoring — voir decision.py. lead.score est déjà
        # pénalisé pour les leads sans CA réel (score_ajuste, appliqué au scoring).
        new_status = decide_status(lead.score, threshold)
        if lead.status != new_status:
            lead.status = new_status
            if new_status == LeadStatus.QUALIFIE:
                qualified += 1
            else:
                rejected += 1

    await db.commit()

    # Un lead nouvellement qualifié n'a pas d'email (il était écarté) : sans
    # tâche de rédaction il resterait QUALIFIE sans suite — bug constaté lors
    # d'une baisse de seuil. On enchaîne automatiquement la rédaction, sauf si
    # un agent travaille déjà sur la campagne (le pipeline s'en chargera).
    redaction_lancee = False
    if qualified > 0 and campaign.status not in ("running", "scoring_pending", "redaction_pending"):
        await create_task(db, campaign_id=campaign.id, agent_name=AgentName.REDACTION, payload={})
        await update_campaign_status(db, campaign, "redaction_pending")
        redaction_lancee = True

    return {
        "qualifies": qualified,
        "rejetes": rejected,
        "total": len(leads),
        "redaction_lancee": redaction_lancee,
    }


@router.post("/{campaign_id}/redact", response_model=CampaignResponse, status_code=202)
async def redact(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user),
):
    """Déclenche (ou re-déclenche) la rédaction des emails pour les leads QUALIFIE."""
    campaign = await get_campaign(db, campaign_id, current_user.id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campagne introuvable")
    if campaign.status in ("running", "redaction_pending"):
        raise HTTPException(status_code=409, detail="Un agent est déjà en cours sur cette campagne")

    await create_task(db, campaign_id=campaign.id, agent_name=AgentName.REDACTION, payload={})
    return await update_campaign_status(db, campaign, "redaction_pending")


@router.delete("/{campaign_id}", status_code=204)
async def delete(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user),
):
    campaign = await get_campaign(db, campaign_id, current_user.id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campagne introuvable")
    await delete_campaign(db, campaign)
