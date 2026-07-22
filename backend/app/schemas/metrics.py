from datetime import datetime

from pydantic import BaseModel


class FunnelMetrics(BaseModel):
    collecte: int
    enrichi: int
    ecarte: int
    qualifie: int
    email_genere: int
    en_attente_validation: int
    valide: int
    rejete: int
    synchronise_crm: int
    contacte: int
    repondu: int
    sans_reponse: int
    # Part des leads scorés qui passent le seuil de qualification.
    taux_qualification: float | None = None
    # Part des emails générés acceptés tels quels (ou modifiés) par le commercial.
    taux_validation_humaine: float | None = None
    # Part des leads contactés ayant obtenu une réponse (won ou message reçu).
    taux_reponse: float | None = None


class ScoringQualityMetrics(BaseModel):
    score_moyen: float | None = None
    confidence_moyenne: float | None = None
    repartition_label: dict[str, int] = {}


class CycleTimeMetrics(BaseModel):
    """Délais moyens (heures) entre étapes du pipeline — mesure directe du
    gain de temps apporté par l'automatisation vs un traitement manuel."""

    delai_moyen_collecte_enrichissement_h: float | None = None
    delai_moyen_enrichissement_scoring_h: float | None = None
    delai_moyen_scoring_redaction_h: float | None = None
    delai_moyen_total_collecte_email_h: float | None = None


class AgentReliabilityMetrics(BaseModel):
    agent_name: str
    total: int
    done: int
    failed: int
    taux_succes: float | None = None
    tentatives_moyennes: float | None = None
    duree_moyenne_s: float | None = None


class CrmSyncMetrics(BaseModel):
    total: int
    success: int
    error: int
    taux_succes: float | None = None


class MetricsResponse(BaseModel):
    generated_at: datetime
    campaign_id: str | None = None
    nb_campagnes: int
    nb_leads_total: int
    funnel: FunnelMetrics
    scoring: ScoringQualityMetrics
    cycle_time: CycleTimeMetrics
    agents: list[AgentReliabilityMetrics]
    crm_sync: CrmSyncMetrics
