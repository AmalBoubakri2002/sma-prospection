import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.agents.crm.sync import historize_email_in_chatter, push_lead_to_odoo
from app.models.campaign import Campaign
from app.models.user import User
from app.services.crm_sync import mark_crm_sync_error, mark_crm_sync_success
from app.services.lead import list_leads_to_sync_crm, update_lead_synced_crm

logger = logging.getLogger("agent-crm")


async def run_crm(db: AsyncSession, campaign: Campaign) -> dict:
    total_synced = 0
    total_errors = 0
    failed_this_run: set = set()

    # Récupéré une seule fois par campagne (pas par lead) : sert à retrouver le
    # vendeur Odoo correspondant, voir sync.py::_get_user_id_by_email.
    commercial = await db.get(User, campaign.commercial_id)
    commercial_email = commercial.email if commercial else None

    while True:
        leads = [
            lead for lead in await list_leads_to_sync_crm(db, campaign.id)
            if lead.id not in failed_this_run
        ]
        if not leads:
            break

        for lead in leads:
            try:
                odoo_lead_id = await push_lead_to_odoo(lead, commercial_email)
                await historize_email_in_chatter(odoo_lead_id, lead.objet_email, lead.contenu_email)
                await mark_crm_sync_success(db, lead.id, odoo_lead_id)
                await update_lead_synced_crm(db, lead)
                total_synced += 1
                logger.debug("Lead %s synchronisé → Odoo #%d", lead.siret, odoo_lead_id)
            except Exception as exc:
                logger.warning("Synchronisation CRM échouée pour %s : %s", lead.siret, exc)
                await mark_crm_sync_error(db, lead.id, str(exc))
                total_errors += 1
                failed_this_run.add(lead.id)

    logger.info(
        "Campagne %s — CRM : %d synchronisés, %d erreurs",
        campaign.id, total_synced, total_errors,
    )
    return {
        "leads_synchronises": total_synced,
        "leads_erreurs": total_errors,
    }
