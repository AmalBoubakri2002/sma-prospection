def dedupe(normalized: list[dict], existing_sirets: set[str]) -> list[dict]:
    """Élimine les doublons par SIRET : ceux déjà en base pour cette campagne,
    et ceux apparaissant plusieurs fois dans le même lot (pages SIRENE qui se recoupent)."""
    seen = set(existing_sirets)
    deduped: list[dict] = []
    for lead in normalized:
        siret = lead.get("siret")
        if not siret or siret in seen:
            continue
        seen.add(siret)
        deduped.append(lead)
    return deduped
