
from app.agents.scoring.feature_spec import clean_financial_value
from app.core.config import settings
from app.models.lead import LeadStatus


def score_ajuste(score: float, ca: float | int | None, resultat_net: float | int | None) -> float:

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
      return (
          LeadStatus.QUALIFIE if round(score, 2) >= round(score_minimum, 2) else LeadStatus.ECARTE
      )


def label_for_score(score: float) -> str:

    if score >= 0.75:
        return "CHAUD"
    if score >= 0.50:
        return "TIEDE"
    if score >= 0.30:
        return "FROID"
    return "HORS_CIBLE"


CONFIDENCE_POIDS_CA = 0.4
CONFIDENCE_POIDS_RN = 0.4
CONFIDENCE_POIDS_CA_N1 = 0.2


def confidence_score(
    ca: float | int | None,
    ca_n1: float | int | None,
    resultat_net: float | int | None,
) -> float:

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
