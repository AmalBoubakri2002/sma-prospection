import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_task import AgentTask, AgentTaskStatus
from app.models.campaign import Campaign
from app.models.crm_sync import CRMSync, CRMSyncStatus
from app.models.lead import Lead, LeadStatus
from app.schemas.metrics import (
    AgentReliabilityMetrics,
    CrmSyncMetrics,
    CycleTimeMetrics,
    FunnelMetrics,
    MetricsResponse,
    ScoringQualityMetrics,
)


def _safe_rate(numerator: int, denominator: int) -> float | None:
    """Taux en %, arrondi à 1 décimale — None si le dénominateur est vide
    (évite d'afficher un faux 0 % quand l'étape n'a simplement pas encore
    d'exemplaire)."""
    if denominator <= 0:
        return None
    return round(numerator / denominator * 100, 1)


def _avg_delay_hours(start_col, end_col):
    """Moyenne SQL du délai (heures) entre deux timestamps — ignore les lignes
    où l'une des deux colonnes est NULL (lead pas encore arrivé à cette étape),
    ce qui est le comportement voulu (pas un délai de zéro)."""
    return func.avg(func.extract("epoch", end_col - start_col) / 3600.0)


async def _get_funnel_metrics(
    db: AsyncSession, campaign_conditions: list, nb_scored: int
) -> FunnelMetrics:
    stmt = (
        select(Lead.status, func.count().label("n"))
        .join(Campaign, Campaign.id == Lead.campaign_id)
        .where(*campaign_conditions)
        .group_by(Lead.status)
    )
    counts = {row.status: row.n for row in (await db.execute(stmt)).all()}

    ecarte = counts.get(LeadStatus.ECARTE, 0)
    valide = counts.get(LeadStatus.VALIDE, 0)
    rejete = counts.get(LeadStatus.REJETE, 0)
    synchronise_crm = counts.get(LeadStatus.SYNCHRONISE_CRM, 0)
    contacte = counts.get(LeadStatus.CONTACTE, 0)
    repondu = counts.get(LeadStatus.REPONDU, 0)
    sans_reponse = counts.get(LeadStatus.SANS_REPONSE, 0)

    # QUALIFIE et VALIDE sont des statuts transitoires : un lead qui a
    # progressé (email envoyé, synchronisé CRM, contacté...) n'est plus dans
    # cet état alors qu'il EST passé par cette étape. D'où des compteurs
    # cumulatifs (au lieu d'un simple ratio sur le statut courant) pour
    # les deux taux ci-dessous — sinon ils retombent artificiellement vers 0
    # au fur et à mesure que le pipeline avance.
    valide_un_jour = valide + synchronise_crm + contacte + repondu + sans_reponse

    return FunnelMetrics(
        collecte=counts.get(LeadStatus.COLLECTE, 0),
        enrichi=counts.get(LeadStatus.ENRICHI, 0),
        ecarte=ecarte,
        qualifie=counts.get(LeadStatus.QUALIFIE, 0),
        email_genere=counts.get(LeadStatus.EMAIL_GENERE, 0),
        en_attente_validation=counts.get(LeadStatus.EN_ATTENTE_VALIDATION, 0),
        valide=valide,
        rejete=rejete,
        synchronise_crm=synchronise_crm,
        contacte=contacte,
        repondu=repondu,
        sans_reponse=sans_reponse,
        taux_qualification=_safe_rate(nb_scored - ecarte, nb_scored),
        taux_validation_humaine=_safe_rate(valide_un_jour, valide_un_jour + rejete),
        taux_reponse=_safe_rate(repondu, repondu + sans_reponse),
    )


async def _get_scoring_quality_metrics(
    db: AsyncSession, campaign_conditions: list
) -> ScoringQualityMetrics:
    avg_stmt = (
        select(func.avg(Lead.score), func.avg(Lead.confidence_score))
        .join(Campaign, Campaign.id == Lead.campaign_id)
        .where(*campaign_conditions, Lead.score.is_not(None))
    )
    avg_score, avg_confidence = (await db.execute(avg_stmt)).one()

    label_stmt = (
        select(Lead.label_scoring, func.count().label("n"))
        .join(Campaign, Campaign.id == Lead.campaign_id)
        .where(*campaign_conditions, Lead.label_scoring.is_not(None))
        .group_by(Lead.label_scoring)
    )
    labels = {row.label_scoring: row.n for row in (await db.execute(label_stmt)).all()}

    return ScoringQualityMetrics(
        score_moyen=round(avg_score, 3) if avg_score is not None else None,
        confidence_moyenne=round(avg_confidence, 1) if avg_confidence is not None else None,
        repartition_label=labels,
    )


async def _get_cycle_time_metrics(
    db: AsyncSession, campaign_conditions: list
) -> CycleTimeMetrics:
    stmt = (
        select(
            _avg_delay_hours(Lead.created_at, Lead.enriched_at).label("collecte_enrichissement"),
            _avg_delay_hours(Lead.enriched_at, Lead.scored_at).label("enrichissement_scoring"),
            _avg_delay_hours(Lead.scored_at, Lead.email_genere_at).label("scoring_redaction"),
            _avg_delay_hours(Lead.created_at, Lead.email_genere_at).label("total_collecte_email"),
        )
        .join(Campaign, Campaign.id == Lead.campaign_id)
        .where(*campaign_conditions)
    )
    row = (await db.execute(stmt)).one()

    def _round(v: float | None) -> float | None:
        return round(v, 2) if v is not None else None

    return CycleTimeMetrics(
        delai_moyen_collecte_enrichissement_h=_round(row.collecte_enrichissement),
        delai_moyen_enrichissement_scoring_h=_round(row.enrichissement_scoring),
        delai_moyen_scoring_redaction_h=_round(row.scoring_redaction),
        delai_moyen_total_collecte_email_h=_round(row.total_collecte_email),
    )


async def _get_agent_reliability_metrics(
    db: AsyncSession, task_conditions: list
) -> list[AgentReliabilityMetrics]:
    counts_stmt = (
        select(AgentTask.agent_name, AgentTask.status, func.count().label("n"))
        .join(Campaign, Campaign.id == AgentTask.campaign_id)
        .where(*task_conditions)
        .group_by(AgentTask.agent_name, AgentTask.status)
    )
    counts_rows = (await db.execute(counts_stmt)).all()

    terminal_stmt = (
        select(
            AgentTask.agent_name,
            func.avg(AgentTask.attempts).label("avg_attempts"),
            func.avg(
                func.extract("epoch", AgentTask.updated_at - AgentTask.created_at)
            ).label("avg_duration_s"),
        )
        .join(Campaign, Campaign.id == AgentTask.campaign_id)
        .where(*task_conditions, AgentTask.status.in_([AgentTaskStatus.DONE, AgentTaskStatus.FAILED]))
        .group_by(AgentTask.agent_name)
    )
    perf_by_agent = {row.agent_name: row for row in (await db.execute(terminal_stmt)).all()}

    by_agent: dict[str, dict[str, int]] = {}
    for row in counts_rows:
        entry = by_agent.setdefault(row.agent_name, {"done": 0, "failed": 0, "other": 0})
        if row.status == AgentTaskStatus.DONE:
            entry["done"] = row.n
        elif row.status == AgentTaskStatus.FAILED:
            entry["failed"] = row.n
        else:
            entry["other"] += row.n

    results = []
    for agent_name in sorted(by_agent):
        entry = by_agent[agent_name]
        done, failed, other = entry["done"], entry["failed"], entry["other"]
        terminal = done + failed
        perf = perf_by_agent.get(agent_name)
        results.append(
            AgentReliabilityMetrics(
                agent_name=agent_name,
                total=done + failed + other,
                done=done,
                failed=failed,
                taux_succes=_safe_rate(done, terminal),
                tentatives_moyennes=(
                    round(perf.avg_attempts, 2)
                    if perf is not None and perf.avg_attempts is not None
                    else None
                ),
                duree_moyenne_s=(
                    round(perf.avg_duration_s, 1)
                    if perf is not None and perf.avg_duration_s is not None
                    else None
                ),
            )
        )
    return results


async def _get_crm_sync_metrics(
    db: AsyncSession, campaign_conditions: list
) -> CrmSyncMetrics:
    stmt = (
        select(CRMSync.sync_status, func.count().label("n"))
        .join(Lead, Lead.id == CRMSync.lead_id)
        .join(Campaign, Campaign.id == Lead.campaign_id)
        .where(*campaign_conditions)
        .group_by(CRMSync.sync_status)
    )
    counts = {row.sync_status: row.n for row in (await db.execute(stmt)).all()}

    success = counts.get(CRMSyncStatus.SUCCESS, 0)
    error = counts.get(CRMSyncStatus.ERROR, 0)
    pending = counts.get(CRMSyncStatus.PENDING, 0)

    return CrmSyncMetrics(
        total=success + error + pending,
        success=success,
        error=error,
        taux_succes=_safe_rate(success, success + error),
    )


async def get_metrics_report(
    db: AsyncSession,
    commercial_id: uuid.UUID,
    campaign_id: uuid.UUID | None = None,
) -> MetricsResponse:
    """Rapport de performance agrégé — scope par défaut : toutes les campagnes
    du commercial connecté, ou une seule campagne si campaign_id est fourni
    (l'appelant doit avoir vérifié au préalable que la campagne lui appartient).
    """
    campaign_conditions = [Campaign.commercial_id == commercial_id]
    if campaign_id is not None:
        campaign_conditions.append(Lead.campaign_id == campaign_id)

    task_conditions = [Campaign.commercial_id == commercial_id]
    if campaign_id is not None:
        task_conditions.append(AgentTask.campaign_id == campaign_id)

    nb_campagnes_stmt = select(func.count(func.distinct(Campaign.id))).where(
        Campaign.commercial_id == commercial_id,
        *([Campaign.id == campaign_id] if campaign_id is not None else []),
    )
    nb_campagnes = (await db.execute(nb_campagnes_stmt)).scalar_one()

    nb_scored_stmt = (
        select(func.count())
        .select_from(Lead)
        .join(Campaign, Campaign.id == Lead.campaign_id)
        .where(*campaign_conditions, Lead.score.is_not(None))
    )
    nb_scored = (await db.execute(nb_scored_stmt)).scalar_one()

    funnel = await _get_funnel_metrics(db, campaign_conditions, nb_scored)
    nb_leads_total = (
        funnel.collecte
        + funnel.enrichi
        + funnel.ecarte
        + funnel.qualifie
        + funnel.email_genere
        + funnel.en_attente_validation
        + funnel.valide
        + funnel.rejete
        + funnel.synchronise_crm
        + funnel.contacte
        + funnel.repondu
        + funnel.sans_reponse
    )

    return MetricsResponse(
        generated_at=datetime.now(timezone.utc),
        campaign_id=str(campaign_id) if campaign_id else None,
        nb_campagnes=nb_campagnes,
        nb_leads_total=nb_leads_total,
        funnel=funnel,
        scoring=await _get_scoring_quality_metrics(db, campaign_conditions),
        cycle_time=await _get_cycle_time_metrics(db, campaign_conditions),
        agents=await _get_agent_reliability_metrics(db, task_conditions),
        crm_sync=await _get_crm_sync_metrics(db, campaign_conditions),
    )
