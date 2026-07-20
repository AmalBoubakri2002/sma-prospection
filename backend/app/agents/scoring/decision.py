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
    On lui retire une marge plutôt que de relever le seuil de qualification pour
    ce lead : le nombre affiché reste ainsi celui qui explique la décision face
    au seuil de campagne, sans seuil caché par lead (cf. cas Slimpay : score brut
    65,15 % au-dessus du seuil affiché 65 % mais écarté — illisible tant que le
    seuil relevé restait invisible en UI).

    Marge graduée sur le résultat net RÉEL (validé équipe métier 2026-07-19,
    paliers ci-dessous) : un RN confirmé n'a rien de fictif — contrairement au
    CA imputé — mais deux leads à RN aussi différents que +2 k€ et +4 M€ ne
    couraient auparavant pas le même risque d'imputation optimiste tout en
    recevant la même marge (cf. cas Ipsosenso, RN +1,2 M€). Un RN inconnu reste
    moins pénalisé qu'un RN négatif confirmé : l'absence de donnée n'est pas une
    confirmation de mauvaise santé financière. resultat_net=0 est une vraie
    valeur (contrairement à ca=0, voir clean_financial_value) mais pas un signal
    de rentabilité : traité comme le reste des RN <= 0, pas comme un RN positif.
    """
    if clean_financial_value(ca) is not None:
        return score
    rn = resultat_net
    if rn is None:
        marge = settings.SCORING_MARGE_SANS_CA_RN_INCONNU
    elif rn > settings.SCORING_RN_SEUIL_TRES_POSITIF:
        marge = settings.SCORING_MARGE_SANS_CA_RN_TRES_POSITIF
    elif rn > 0:
        marge = settings.SCORING_MARGE_SANS_CA_RN_POSITIF
    elif rn >= settings.SCORING_RN_SEUIL_TRES_NEGATIF:
        marge = settings.SCORING_MARGE_SANS_CA_RN_NEGATIF
    else:
        marge = settings.SCORING_MARGE_SANS_CA_RN_TRES_NEGATIF
    return max(0.0, score - marge)


def decide_status(score: float, score_minimum: float) -> str:
    """ECARTE = rejet automatique (score < seuil) ; REJETE reste réservé au rejet
    humain explicite. `score` doit déjà avoir été passé par score_ajuste."""
    return LeadStatus.QUALIFIE if round(score, 2) >= round(score_minimum, 2) else LeadStatus.ECARTE


def label_for_score(score: float) -> str:
    """CHAUD/TIEDE/FROID/HORS_CIBLE affiché à l'écran — `score` doit déjà avoir
    été passé par score_ajuste, comme decide_status. Calculer ce label sur la
    sortie brute du modèle (avant ajustement CA manquant) produisait des
    incohérences visibles (ex: badge CHAUD à côté d'un score ECARTE)."""
    if score >= 0.75:
        return "CHAUD"
    if score >= 0.50:
        return "TIEDE"
    if score >= 0.30:
        return "FROID"
    return "HORS_CIBLE"


# Poids du score de confiance — CA et RN à poids égal (les deux blocs dominants
# du barème métier, cf. dataset_pipeline.py::_compute_raw_score), CA N-1 en
# poids réduit car il n'alimente que croissance_ca, une feature annexe du
# modèle (groupe SHAP "croissance", distinct de "financier_ca"/"financier_rn").
CONFIDENCE_POIDS_CA = 0.4
CONFIDENCE_POIDS_RN = 0.4
CONFIDENCE_POIDS_CA_N1 = 0.2


def confidence_score(
    ca: float | int | None,
    ca_n1: float | int | None,
    resultat_net: float | int | None,
) -> float:
    """Score de confiance (0-100) affiché à côté du score — quelle part des
    données FINANCIÈRES du lead est réelle plutôt qu'imputée, pour qu'un
    commercial ne traite pas un score bâti sur un CA/RN imputés comme aussi
    fiable qu'un score construit sur des données confirmées.

    Ne porte que sur ca/ca_n1/resultat_net : les autres features du modèle
    (âge, taille, secteur) viennent du stock SIRENE et sont quasi toujours
    disponibles en pratique (voir feature_spec.py) — les inclure diluerait le
    signal sans réduire l'incertitude réelle, qui vient des seules données
    dépendant de l'enrichissement API. a_ca_n1 suit exactement la même
    définition que dans feature_builder.py (ca_n1 is not None, sans nettoyage
    du zéro) pour refléter ce que le modèle a réellement vu comme "connu".
    """
    a_ca = float(clean_financial_value(ca) is not None)
    a_ca_n1 = float(ca_n1 is not None)
    a_rn = float(resultat_net is not None)
    return round(
        100 * (
            CONFIDENCE_POIDS_CA * a_ca +
            CONFIDENCE_POIDS_RN * a_rn +
            CONFIDENCE_POIDS_CA_N1 * a_ca_n1
        ),
        1,
    )
