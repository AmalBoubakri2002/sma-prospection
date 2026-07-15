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

    # Dédup inter-campagnes : une entreprise dont un lead est encore actif dans
    # une autre campagne n'est pas recollectée (sinon doublons Odoo + prospect
    # recontacté par email). Écartés/rejetés ailleurs restent prospectables.
    # L'exclusion est passée à SIRENE pour que la pagination avance jusqu'à
    # trouver des entreprises réellement nouvelles.
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

    # Mémorise le plafond réel SIRENE pour l'afficher dans le dashboard.
    if total_sirene and campaign.estimated_prospects != total_sirene:
        campaign.estimated_prospects = total_sirene
        db.add(campaign)
        await db.commit()

    normalized = [normalize_etablissement(e) for e in raw_etablissements]
    normalized = [lead for lead in normalized if lead["siret"]]
    # La requête Sirene matche periode(activitePrincipaleEtablissement:...), donc
    # un établissement reclassé depuis peut matcher sur un NAF qu'il n'a plus —
    # normalize_etablissement stocke lui le NAF ACTUEL (_current_periode). On
    # revérifie ici que le NAF stocké est bien dans la cible de la campagne,
    # pour ne pas garder des leads dont le secteur affiché est hors périmètre
    # (cf. Aboca S.P.A. en 46.46Z / Numberly en 63.11Z sur une campagne 70.22Z-73.20Z).
    normalized = [lead for lead in normalized if lead["secteur"] in campaign.codes_naf]
    nouveaux = dedupe(normalized, sirets_bloques)

    created = await bulk_create_leads(db, campaign.id, nouveaux)

    return {
        "leads_collected": len(created),
        "leads_bruts_recus": len(raw_etablissements),
        "total_sirene_disponible": total_sirene,
    }
