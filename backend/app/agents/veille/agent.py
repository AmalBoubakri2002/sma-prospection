from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.veille.deduplicator import dedupe
from app.agents.veille.normalizer import normalize_etablissement
from app.agents.veille.sirene import SireneClient
from app.models.campaign import Campaign
from app.services.lead import (
    bulk_create_leads,
    count_usable_leads_for_campaign,
    get_existing_sirets,
    get_sirets_prospected_elsewhere,
)


async def run_veille(db: AsyncSession, campaign: Campaign) -> dict:

    existing_sirets = await get_existing_sirets(db, campaign.id)

    usable_count = await count_usable_leads_for_campaign(db, campaign.id)
    quota_restant = max(campaign.quota - usable_count, 0)
    if quota_restant == 0:
        return {"leads_collected": 0, "raison": "quota déjà atteint"}

    sirets_ailleurs = await get_sirets_prospected_elsewhere(db, campaign.id)
    sirets_bloques = existing_sirets | sirets_ailleurs

    client = SireneClient()
    raw_etablissements, total_sirene = await client.search_etablissements(
        codes_naf=campaign.codes_naf,
        codes_postaux=campaign.codes_postaux,
        tranches_effectifs=campaign.tranches_effectifs,
        quota=quota_restant,
        exclude_sirets=sirets_bloques,
    )

    if total_sirene and campaign.estimated_prospects != total_sirene:
        campaign.estimated_prospects = total_sirene
        db.add(campaign)
        await db.commit()

    normalized = [normalize_etablissement(e) for e in raw_etablissements]
    nouveaux = dedupe(normalized, sirets_bloques)

    created = await bulk_create_leads(db, campaign.id, nouveaux)

    return {
        "leads_collected": len(created),
        "leads_bruts_recus": len(raw_etablissements),
        "total_sirene_disponible": total_sirene,
    }
