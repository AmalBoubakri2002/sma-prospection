from app.agents.enrichissement.email_guesser import extract_domain, guess_email


def test_extract_domain_https_www():
    assert extract_domain("https://www.example.fr") == "example.fr"


def test_extract_domain_plain():
    assert extract_domain("example.com") == "example.com"


def test_extract_domain_with_path():
    assert extract_domain("https://company.io/contact") == "company.io"


def test_extract_domain_none():
    assert extract_domain(None) is None


def test_extract_domain_empty():
    assert extract_domain("") is None


def test_guess_email_nominal():
    assert guess_email("Jean", "DUPONT", "https://www.dupont.fr") == "jean.dupont@dupont.fr"


def test_guess_email_accents():
    assert guess_email("Élodie", "Lefèvre", "https://lefebvre.fr") == "elodie.lefevre@lefebvre.fr"


def test_guess_email_hyphen_prenom():
    assert guess_email("Jean-Pierre", "MARTIN", "martin.fr") == "jean-pierre.martin@martin.fr"


def test_guess_email_no_site():
    assert guess_email("Jean", "DUPONT", None) is None


def test_guess_email_no_prenom():
    assert guess_email(None, "DUPONT", "https://dupont.fr") is None


def test_guess_email_no_nom():
    assert guess_email("Jean", None, "https://dupont.fr") is None
