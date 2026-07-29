def dedupe(normalized: list[dict], existing_sirets: set[str]) -> list[dict]:

    seen = set(existing_sirets)
    deduped: list[dict] = []
    for lead in normalized:
        siret = lead.get("siret")
        if not siret or siret in seen:
            continue
        seen.add(siret)
        deduped.append(lead)
    return deduped
