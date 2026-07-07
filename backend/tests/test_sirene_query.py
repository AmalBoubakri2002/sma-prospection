from app.agents.veille.sirene import build_query


def test_single_criteria_per_field():
    query = build_query(["62.01Z"], ["75008"], ["12"])
    assert query == (
        "periode(activitePrincipaleEtablissement:62.01Z) AND "
        "codePostalEtablissement:75008 AND "
        "trancheEffectifsEtablissement:12 AND "
        "periode(etatAdministratifEtablissement:A)"
    )


def test_naf_requires_periode_wrapper():
    """activitePrincipaleEtablissement n'est exposé par l'API Sirene qu'à
    l'intérieur de periodesEtablissement — une requête sans periode(...) est
    rejetée en 400 par l'API (testé en prod le 2026-07-07). Le filtrage sur le
    NAF ACTUEL (vs historique) se fait en aval sur le résultat, pas ici — voir
    veille/agent.py::run_veille."""
    query = build_query(["62.01Z"], ["75008"], ["12"])
    assert "periode(activitePrincipaleEtablissement:62.01Z)" in query


def test_multiple_values_combined_with_or():
    query = build_query(["62.01Z", "62.02A"], ["75008", "75009"], ["12"])
    assert (
        "(periode(activitePrincipaleEtablissement:62.01Z) OR "
        "periode(activitePrincipaleEtablissement:62.02A))"
    ) in query
    assert "(codePostalEtablissement:75008 OR codePostalEtablissement:75009)" in query


def test_active_establishments_only():
    query = build_query(["62.01Z"], ["75008"], ["12"])
    assert "periode(etatAdministratifEtablissement:A)" in query
