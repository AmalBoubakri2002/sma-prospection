from app.agents.enrichissement.email_scraper import _EMAIL_RE, _GENERIC_PREFIXES


def test_email_regex_finds_address():
    html = '<p>Contactez-nous : jean.dupont@example.fr</p>'
    found = _EMAIL_RE.findall(html)
    assert "jean.dupont@example.fr" in found


def test_email_regex_ignores_html_entities():
    html = "Écrivez à prenom.nom&#64;example.com"
    # L'entité HTML n'est pas décodée — la regex ne trouve rien
    found = _EMAIL_RE.findall(html)
    assert not any("example.com" in e for e in found)


def test_generic_prefixes_filtered():
    assert "noreply" in _GENERIC_PREFIXES
    assert "contact" in _GENERIC_PREFIXES
    assert "support" in _GENERIC_PREFIXES


def test_jean_dupont_not_generic():
    assert "jean.dupont" not in _GENERIC_PREFIXES
