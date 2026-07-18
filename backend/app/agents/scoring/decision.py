# Décision QUALIFIE/ECARTE partagée entre l'Agent Scoring (agent.py) et le
# reclassement après changement de seuil (endpoints/campaigns.py::requalify) —
# si les deux divergeaient, un « Réappliquer » depuis l'UI annulerait la règle
# appliquée au moment du scoring.

from app.agents.scoring.feature_spec import clean_financial_value
from app.core.config import settings
from app.models.lead import LeadStatus


def score_ajuste(score: float, ca: float | int | None, resultat_net: float | int | None) -> float:
    """Score final d'un lead — celui stocké dans lead.score, affiché à l'écran
    et comparé au seuil de campagne.

    Un lead sans CA réel (None ou 0, cf. clean_financial_value) est scoré sur un
    CA imputé — son score brut repose donc en partie sur des données fictives.
    On lui retire une marge (SCORING_MARGE_SEUIL_SANS_CA) plutôt que de relever
    le seuil de qualification pour ce lead : le nombre affiché reste ainsi celui
    qui explique la décision face au seuil de campagne, sans seuil caché par
    lead (cf. cas Slimpay : score brut 65,15 % au-dessus du seuil affiché 65 %
    mais écarté — illisible tant que le seuil relevé restait invisible en UI).

    Marge réduite (SCORING_MARGE_SEUIL_SANS_CA_AVEC_RN_POSITIF) quand un
    résultat net RÉEL et POSITIF est disponible malgré le CA manquant (cf. cas
    Ipsosenso) : ce n'est pas un lead sans finances, c'est un lead à données
    partielles. Un RN positif n'a rien de fictif — contrairement au CA imputé —
    et pèse plus lourd que le CA dans le barème métier (résultat net : jusqu'à
    30 pts/100, contre 20 pour le CA — voir dataset_pipeline.py::_compute_raw_score).
    Un RN manquant ou négatif garde la marge pleine : rien ne justifie plus
    d'indulgence qu'un lead sans aucune donnée financière. resultat_net=0 est
    une vraie valeur (contrairement à ca=0, voir clean_financial_value), donc
    testé strictement >0, pas juste "not None".
    """
    if clean_financial_value(ca) is not None:
        return score
    marge = (
        settings.SCORING_MARGE_SEUIL_SANS_CA_AVEC_RN_POSITIF
        if resultat_net is not None and resultat_net > 0
        else settings.SCORING_MARGE_SEUIL_SANS_CA
    )
    return max(0.0, score - marge)


def decide_status(score: float, score_minimum: float) -> str:
    """ECARTE = rejet automatique (score < seuil) ; REJETE reste réservé au rejet
    humain explicite. `score` doit déjà avoir été passé par score_ajuste."""
    return LeadStatus.QUALIFIE if round(score, 2) >= round(score_minimum, 2) else LeadStatus.ECARTE
