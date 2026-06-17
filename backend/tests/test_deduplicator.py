from app.agents.veille.deduplicator import dedupe


def test_filters_out_existing_sirets():
    normalized = [{"siret": "111"}, {"siret": "222"}]
    result = dedupe(normalized, existing_sirets={"111"})
    assert result == [{"siret": "222"}]


def test_filters_out_duplicates_within_batch():
    normalized = [{"siret": "111"}, {"siret": "111"}, {"siret": "222"}]
    result = dedupe(normalized, existing_sirets=set())
    assert [r["siret"] for r in result] == ["111", "222"]


def test_no_duplicates_returns_all():
    normalized = [{"siret": "111"}, {"siret": "222"}]
    result = dedupe(normalized, existing_sirets=set())
    assert result == normalized
