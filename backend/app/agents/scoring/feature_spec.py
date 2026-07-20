import math

TAILLE_TO_CODE: dict[str, int] = {
    "NN": 0, "01": 0, "02": 0, "03": 0,   # TPE / micro
    "11": 1, "12": 1,                       # PE  (6–19 salariés)
    "21": 2, "22": 2, "31": 2,              # ME  (20–199 salariés)
    "32": 3, "41": 3, "42": 3,              # ETI (200–999 salariés)
    "51": 4, "52": 4, "53": 4,              # GE  (1000+ salariés)
}

# Effectif représentatif (médiane approx. de la tranche INSEE officielle) —
# sert uniquement à dériver ca_par_salarie_log1p, pas à remplacer taille_code.
TAILLE_MIDPOINT: dict[str, int] = {
    "NN": 5, "00": 0, "01": 1, "02": 4, "03": 7,
    "11": 15, "12": 35,
    "21": 75, "22": 150, "31": 225, "32": 375,
    "41": 750, "42": 1500,
    "51": 3500, "52": 7500, "53": 15000,
}

# Winsorisation : le ratio résultat_net/ca explose quand ca est proche de 0.
MARGE_NETTE_CLIP = 1.5

FEATURE_NAMES = [
    "ca_log1p",        # CA transformé (log-normal → quasi-normal), imputé médiane
    "a_ca",            # flag: ca était disponible avant imputation médiane
    "ca_n1_log1p",     # CA N-1 transformé, imputé médiane
    "a_ca_n1",         # flag: ca_n1 était disponible
    "rn_signed_log1p", # résultat net signé log-transformé, imputé 0
    "a_resultat_net",  # flag: résultat_net était disponible
    "marge_nette",     # marge nette winsorisée [-1.5, 1.5], imputée médiane
    "croissance_ca",   # taux de croissance, imputé 0 (absence = inconnu)
    "age_entreprise",  # âge en années, imputé médiane
       "taille_code",     # ordinal 0 (TPE) → 4 (GE)
    "secteur_code",    # division NAF (2 chiffres) — évite la sparsité du code sous-classe complet
    "ca_par_salarie_log1p",  # CA / effectif représentatif — ratio explicite plutôt
                              # qu'une interaction implicite taille_code × ca_log1p
]


def naf_division(secteur: str | None) -> str:
    """Réduit un code NAF sous-classe (ex: '6201Z') à sa division INSEE (ex: '62'),
    pour éviter la sparsité de centaines de sous-classes peu représentées."""
    s = str(secteur or "")
    return s[:2] if len(s) >= 2 and s[:2].isdigit() else "00"


def signed_log1p(x: float | None) -> float:
    """log1p qui préserve le signe — gère les résultats nets négatifs."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return 0.0
    return math.copysign(math.log1p(abs(x)), x)


def ca_median_for_taille(medians: dict, taille: str | None) -> float:
  
    group = str(TAILLE_TO_CODE.get(str(taille or "NN"), 0))
    return float(medians.get("ca_par_taille", {}).get(group, medians["ca"]))


def clean_financial_value(x: float | int | None) -> float | int | None:
   
    if x is None:
        return None
    if x == 0:
        return None
    return x
