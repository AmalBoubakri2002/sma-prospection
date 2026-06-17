from app.agents.enrichissement.inpi import _extract_latest_finances, _to_int


def test_extract_latest_finances_nominal():
    bilans = [
        {"dateCloture": "2022-12-31", "chiffreAffaires": 1000000, "resultatNet": 50000},
        {"dateCloture": "2023-12-31", "chiffreAffaires": 1500000, "resultatNet": 80000},
    ]
    result = _extract_latest_finances(bilans)
    assert result["ca"] == 1500000
    assert result["resultat_net"] == 80000


def test_extract_latest_finances_empty():
    assert _extract_latest_finances([]) == {}
    assert _extract_latest_finances({}) == {}


def test_extract_latest_finances_missing_ca():
    bilans = [{"dateCloture": "2023-12-31", "resultatNet": 10000}]
    result = _extract_latest_finances(bilans)
    assert result["ca"] is None
    assert result["resultat_net"] == 10000


def test_to_int_nominal():
    assert _to_int(1500000) == 1500000
    assert _to_int("2500000") == 2500000
    assert _to_int(1500000.0) == 1500000


def test_to_int_none():
    assert _to_int(None) is None
    assert _to_int("") is None
