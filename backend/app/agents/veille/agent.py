from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.veille.deduplicator import dedupe
from app.agents.veille.normalizer import normalize_etablissement
from app.agents.veille.sirene import SireneClient
from app.models.campaign import Campaign
from app.services.lead import bulk_create_leads, count_usable_leads_for_campaign, get_existing_sirets


async def run_veille(db: AsyncSession, campaign: Campaign) -> dict:
    """Étape 1 du pipeline : collecte SIRENE → normalisation → dédup → stockage.
    Retourne un résumé ; lève une exception en cas d'échec (gérée par le worker)."""
    existing_sirets = await get_existing_sirets(db, campaign.id)

    # Le quota se mesure aux leads encore "utiles" (count_usable_leads_for_campaign
    # exclut ceux déjà écartés faute de CA/résultat net), PAS au total brut jamais
    # collecté — sinon une relance de Veille pour compenser ces pertes (voir
    # pipeline_graph.py::node_check_quota) se croit systématiquement déjà au
    # quota et ne collecte jamais rien de plus, puisque len(existing_sirets)
    # inclut aussi les SIRET déjà écartés. La dédup, elle, reste sur
    # `existing_sirets` en entier : on ne veut jamais recollecter un SIRET déjà
    # vu, utile ou non.
    usable_count = await count_usable_leads_for_campaign(db, campaign.id)
    quota_restant = max(campaign.quota - usable_count, 0)
    if quota_restant == 0:
        return {"leads_collected": 0, "raison": "quota déjà atteint"}

    client = SireneClient()
    raw_etablissements, total_sirene = await client.search_etablissements(
        codes_naf=campaign.codes_naf,
        codes_postaux=campaign.codes_postaux,
        tranches_effectifs=campaign.tranches_effectifs,
        quota=quota_restant,
    )

    # Mémorise le plafond réel SIRENE pour l'afficher dans le dashboard.
    if total_sirene and campaign.estimated_prospects != total_sirene:
        campaign.estimated_prospects = total_sirene
        db.add(campaign)
        await db.commit()

    normalized = [normalize_etablissement(e) for e in raw_etablissements]
    normalized = [lead for lead in normalized if lead["siret"]]
    nouveaux = dedupe(normalized, existing_sirets)

    created = await bulk_create_leads(db, campaign.id, nouveaux)

    return {
        "leads_collected": len(created),
        "leads_bruts_recus": len(raw_etablissements),
        "total_sirene_disponible": total_sirene,
    }
