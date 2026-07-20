import uuid
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.lead import Lead, LeadStatus


async def count_leads_by_status_for_campaign(
    db: AsyncSession, campaign_id: uuid.UUID
) -> dict[str, int]:
    """Retourne {statut: nombre} pour tous les leads d'une campagne.
    Utilisé par GET /campaigns/{id}/status pour la barre de progression."""
    result = await db.execute(
        select(Lead.status, func.count().label("n"))
        .where(Lead.campaign_id == campaign_id)
        .group_by(Lead.status)
    )
    return {row.status: row.n for row in result.all()}


async def get_existing_sirets(db: AsyncSession, campaign_id: uuid.UUID) -> set[str]:
    result = await db.execute(select(Lead.siret).where(Lead.campaign_id == campaign_id))
    return set(result.scalars().all())


async def get_sirets_prospected_elsewhere(
    db: AsyncSession, exclude_campaign_id: uuid.UUID
) -> set[str]:
    """SIRET déjà en prospection dans d'AUTRES campagnes — la Veille ne doit
    pas recollecter une entreprise dont un lead est encore actif ailleurs :
    c'est ce qui créait des fiches Odoo en double et des prospects recontactés
    par email (constaté le 2026-07-15 : jusqu'à 4 fiches Odoo pour un même
    SIRET, dont une déjà gagnée). Seuls ECARTE (rejet scoring) et REJETE
    (rejet commercial) libèrent l'entreprise pour une nouvelle prospection."""
    stmt = (
        select(Lead.siret)
        .distinct()
        .where(
            Lead.campaign_id != exclude_campaign_id,
            Lead.status.not_in([LeadStatus.ECARTE, LeadStatus.REJETE]),
        )
    )
    result = await db.execute(stmt)
    return set(result.scalars().all())


async def count_sirets_in_prospection_matching(
    db: AsyncSession, codes_naf: list[str], codes_postaux: list[str]
) -> int:
    """Estimation du recouvrement pour l'écran de création de campagne :
    entreprises déjà en prospection (statut hors ECARTE/REJETE) dont le secteur
    ET le code postal correspondent aux critères visés. Le code postal est
    cherché dans l'adresse (pas de colonne dédiée) — approximation suffisante
    pour annoncer le vivier disponible avant le lancement."""
    if not codes_naf or not codes_postaux:
        return 0
    stmt = select(func.count(func.distinct(Lead.siret))).where(
        Lead.status.not_in([LeadStatus.ECARTE, LeadStatus.REJETE]),
        Lead.secteur.in_(codes_naf),
        or_(*[Lead.adresse.ilike(f"%{cp}%") for cp in codes_postaux]),
    )
    result = await db.execute(stmt)
    return result.scalar_one()


async def count_usable_leads_for_campaign(db: AsyncSession, campaign_id: uuid.UUID) -> int:
    """Nombre de leads collectés qui comptent encore pour le quota — exclut les
    leads ECARTE avec score NULL. Depuis le 2026-07-06, l'Agent Enrichissement
    ne produit plus ce cas (tout lead est scoré, même avec CA/résultat net
    manquants, voir agent.py::_has_sufficient_financials) ; ce filtre ne
    concerne donc que d'éventuels leads historiques créés avant ce changement.

    À NE PAS utiliser pour la déduplication SIRET (get_existing_sirets reste
    la source pour ça, sur TOUS les statuts) — seulement pour décider combien
    de SIRET supplémentaires Veille doit aller chercher pour compenser cette
    perte (voir run_veille + workers/pipeline_graph.py::node_check_quota)."""
    result = await db.execute(
        select(func.count())
        .select_from(Lead)
        .where(
            Lead.campaign_id == campaign_id,
            ~((Lead.status == LeadStatus.ECARTE) & (Lead.score.is_(None))),
        )
    )
    return result.scalar_one()


async def bulk_create_leads(
    db: AsyncSession, campaign_id: uuid.UUID, leads: list[dict]
) -> list[Lead]:
    if not leads:
        return []
    objects = [Lead(campaign_id=campaign_id, **data) for data in leads]
    db.add_all(objects)
    await db.commit()
    for obj in objects:
        await db.refresh(obj)
    return objects


async def count_leads_for_campaign(db: AsyncSession, campaign_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count()).select_from(Lead).where(Lead.campaign_id == campaign_id)
    )
    return result.scalar_one()


async def count_leads_by_campaign(
    db: AsyncSession, commercial_id: uuid.UUID
) -> dict[uuid.UUID, int]:
    """Compte les leads de chaque campagne d'un commercial, en une seule requête."""
    result = await db.execute(
        select(Lead.campaign_id, func.count())
        .join(Campaign, Campaign.id == Lead.campaign_id)
        .where(Campaign.commercial_id == commercial_id)
        .group_by(Lead.campaign_id)
    )
    return dict(result.all())


async def list_leads(
    db: AsyncSession,
    commercial_id: uuid.UUID,
    campaign_id: uuid.UUID | None = None,
    status: str | None = None,
    sort_by_score: bool = False,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Lead], int]:
    base = select(Lead).join(Campaign, Campaign.id == Lead.campaign_id).where(
        Campaign.commercial_id == commercial_id
    )
    if campaign_id:
        base = base.where(Lead.campaign_id == campaign_id)
    if status:
        base = base.where(Lead.status == status)

    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = count_result.scalar_one()

    order = Lead.score.desc().nulls_last() if sort_by_score else Lead.created_at.desc()
    stmt = base.order_by(order).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def list_leads_to_enrich(
    db: AsyncSession, campaign_id: uuid.UUID, page_size: int = 50
) -> list[Lead]:
    """Leads en statut COLLECTE pour une campagne — entrée de l'Agent Enrichissement."""
    stmt = (
        select(Lead)
        .where(Lead.campaign_id == campaign_id, Lead.status == LeadStatus.COLLECTE)
        .order_by(Lead.created_at.asc())
        .limit(page_size)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


_REUSABLE_FIELDS = (
    "telephone", "site_web", "email",
    "prenom_dirigeant", "nom_dirigeant", "titre_dirigeant",
    "ca", "resultat_net", "ca_n1",
    "latitude", "longitude", "date_creation",
)


async def get_enriched_fields_by_siret(db: AsyncSession, siret: str) -> dict | None:
    """Renvoie les champs enrichis du lead le plus récent avec ce SIRET (status=ENRICHI).

    Évite de re-scraper un SIRET déjà enrichi dans une autre campagne et garantit
    la cohérence (même téléphone, même email, même date_creation) entre campagnes."""
    stmt = (
        select(Lead)
        .where(Lead.siret == siret, Lead.status == LeadStatus.ENRICHI)
        .order_by(Lead.enriched_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing is None:
        return None
    return {f: getattr(existing, f) for f in _REUSABLE_FIELDS if getattr(existing, f) is not None}


async def update_lead_enriched(
    db: AsyncSession, lead: Lead, fields: dict, status: str = LeadStatus.ENRICHI
) -> Lead:
    """Met à jour les champs enrichis et passe le lead au statut donné (ENRICHI
    dans tous les cas depuis le 2026-07-06 : même un lead sans CA/résultat net
    atteint l'Agent Scoring, voir agent.py::_has_sufficient_financials — seul
    un échec technique (timeout/erreur) peut encore le laisser ENRICHI sans
    données)."""
    for key, value in fields.items():
        if value is not None:
            setattr(lead, key, value)
    lead.status = status
    lead.enriched_at = datetime.now(timezone.utc)
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    return lead


async def list_leads_to_score(
    db: AsyncSession, campaign_id: uuid.UUID, page_size: int = 50
) -> list[Lead]:
    """Leads en statut ENRICHI pour une campagne — entrée de l'Agent Scoring."""
    stmt = (
        select(Lead)
        .where(Lead.campaign_id == campaign_id, Lead.status == LeadStatus.ENRICHI)
        .order_by(Lead.enriched_at.asc())
        .limit(page_size)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_lead_scored(
    db: AsyncSession,
    lead: Lead,
    score: float,
    label: str,
    status: str = LeadStatus.QUALIFIE,
    shap_json: str | None = None,
    confidence: float | None = None,
) -> Lead:
    """Écrit le score XGBoost (+ SHAP) et passe le lead en QUALIFIE ou ECARTE selon le seuil."""
    lead.score = score
    lead.label_scoring = label
    lead.confidence_score = confidence
    lead.status = status
    lead.scored_at = datetime.now(timezone.utc)
    if shap_json is not None:
        lead.shap_explication = shap_json
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    return lead


async def list_leads_to_redact(
    db: AsyncSession, campaign_id: uuid.UUID, page_size: int = 50
) -> list[Lead]:
    """Leads en statut QUALIFIE pour une campagne — entrée de l'Agent Rédaction."""
    stmt = (
        select(Lead)
        .where(Lead.campaign_id == campaign_id, Lead.status == LeadStatus.QUALIFIE)
        .order_by(Lead.scored_at.asc())
        .limit(page_size)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_lead_email_genere(
    db: AsyncSession, lead: Lead, objet: str, contenu: str
) -> Lead:
    """Écrit l'email généré et place le lead en EN_ATTENTE_VALIDATION (file de validation)."""
    lead.objet_email = objet
    lead.contenu_email = contenu
    lead.email_genere_at = datetime.now(timezone.utc)
    lead.status = LeadStatus.EN_ATTENTE_VALIDATION
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    return lead


async def update_lead_email_content(
    db: AsyncSession, lead: Lead, objet: str, contenu: str
) -> Lead:
    """Modifie l'email d'un lead sans changer son statut (action 'Modifier' du commercial)."""
    lead.objet_email = objet
    lead.contenu_email = contenu
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    return lead


async def list_leads_to_sync_crm(
    db: AsyncSession, campaign_id: uuid.UUID, page_size: int = 50
) -> list[Lead]:
    """Leads en statut VALIDE pour une campagne — entrée de l'Agent CRM."""
    stmt = (
        select(Lead)
        .where(Lead.campaign_id == campaign_id, Lead.status == LeadStatus.VALIDE)
        .order_by(Lead.created_at.asc())
        .limit(page_size)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_lead_synced_crm(db: AsyncSession, lead: Lead) -> Lead:
    """Passe le lead en SYNCHRONISE_CRM une fois le push Odoo réussi."""
    lead.status = LeadStatus.SYNCHRONISE_CRM
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    return lead


async def update_lead_contacted(db: AsyncSession, lead: Lead) -> Lead:
    """Passe le lead en CONTACTE une fois l'email envoyé par le module mail d'Odoo."""
    lead.status = LeadStatus.CONTACTE
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    return lead


# Statuts d'un lead encore "vivant" pour le commercial : ni écarté/rejeté
# (hors cible), ni déjà résolu côté CRM (répondu/sans réponse).
_STATUTS_ACTIFS = {
    LeadStatus.QUALIFIE, LeadStatus.EMAIL_GENERE, LeadStatus.EN_ATTENTE_VALIDATION,
    LeadStatus.VALIDE, LeadStatus.SYNCHRONISE_CRM, LeadStatus.CONTACTE,
}


async def get_leads_stats(db: AsyncSession, commercial_id: uuid.UUID) -> dict:
    """Agrégats KPI pour le dashboard commercial — centrés sur l'activité du
    commercial (backlog à traiter, priorité IA, effort de contact, résultat),
    et non sur le détail d'une campagne donnée."""
    base = (
        select(Lead.status, func.count().label("n"))
        .join(Campaign, Campaign.id == Lead.campaign_id)
        .where(Campaign.commercial_id == commercial_id)
        .group_by(Lead.status)
    )
    result = await db.execute(base)
    counts: dict[str, int] = {r.status: r.n for r in result.all()}

    # Leads à traiter : emails générés en attente d'une décision du commercial.
    leads_a_traiter = counts.get(LeadStatus.EN_ATTENTE_VALIDATION, 0)

    # Leads à fort potentiel : label CHAUD parmi les leads encore actifs — ce que
    # l'IA recommande de prioriser, indépendamment de l'étape où ils se trouvent.
    fort_potentiel_query = (
        select(func.count())
        .select_from(Lead)
        .join(Campaign, Campaign.id == Lead.campaign_id)
        .where(
            Campaign.commercial_id == commercial_id,
            Lead.label_scoring == "CHAUD",
            Lead.status.in_(_STATUTS_ACTIFS),
        )
    )
    leads_fort_potentiel = (await db.execute(fort_potentiel_query)).scalar_one()

    # Leads contactés : tout lead pour lequel un email de prospection a été
    # envoyé via le CRM, quel que soit le résultat (répondu, sans réponse, ou
    # encore en attente de réponse).
    nb_contacte = counts.get(LeadStatus.CONTACTE, 0)
    nb_repondu = counts.get(LeadStatus.REPONDU, 0)
    nb_sans_reponse = counts.get(LeadStatus.SANS_REPONSE, 0)
    leads_contactes = nb_contacte + nb_repondu + nb_sans_reponse

    # Taux de réponse : part des leads contactés ayant effectivement répondu.
    taux_reponse = round(nb_repondu / leads_contactes * 100, 1) if leads_contactes > 0 else None

    return {
        "leads_a_traiter": leads_a_traiter,
        "leads_fort_potentiel": leads_fort_potentiel,
        "leads_contactes": leads_contactes,
        "taux_reponse": taux_reponse,
    }


