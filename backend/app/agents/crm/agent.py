import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.crm.sync import (
    find_crm_duplicate,
    historize_email_in_chatter,
    push_lead_to_odoo,
    send_prospection_email,
)
from app.core.config import settings
from app.models.campaign import Campaign
from app.models.user import User
from app.services.crm_sync import mark_crm_sync_error, mark_crm_sync_success
from app.services.lead import (
    list_leads_to_sync_crm,
    update_lead_contacted,
    update_lead_synced_crm,
)

logger = logging.getLogger("agent-crm")


async def run_crm(db: AsyncSession, campaign: Campaign) -> dict:
    total_synced = 0
    total_errors = 0
    total_duplicates = 0
    total_emails_sent = 0
    total_email_errors = 0
    failed_this_run: set = set()

    # Récupéré une seule fois par campagne : sert à retrouver le vendeur Odoo.
    commercial = await db.get(User, campaign.commercial_id)
    commercial_email = commercial.email if commercial else None
    email_from = commercial_email or settings.ODOO_EMAIL_FROM_DEFAULT

    while True:
        leads = [
            lead for lead in await list_leads_to_sync_crm(db, campaign.id)
            if lead.id not in failed_this_run
        ]
        if not leads:
            break

        for lead in leads:
            try:
              
                duplicate_id = await find_crm_duplicate(lead)
                if duplicate_id is not None:
                    await mark_crm_sync_success(db, lead.id, duplicate_id)
                    await update_lead_synced_crm(db, lead)
                    total_duplicates += 1
                    logger.info(
                        "Lead %s — entreprise déjà dans Odoo (fiche #%d), "
                        "rattachement sans doublon ni email",
                        lead.siret, duplicate_id,
                    )
                    continue

                odoo_lead_id = await push_lead_to_odoo(lead, commercial_email)
                await historize_email_in_chatter(
                    odoo_lead_id, lead.objet_email, lead.contenu_email, commercial_email
                )
                await mark_crm_sync_success(db, lead.id, odoo_lead_id)
                await update_lead_synced_crm(db, lead)
                total_synced += 1
                logger.debug("Lead %s synchronisé → Odoo #%d", lead.siret, odoo_lead_id)
            except Exception as exc:
                logger.warning("Synchronisation CRM échouée pour %s : %s", lead.siret, exc)
                await mark_crm_sync_error(db, lead.id, str(exc))
                total_errors += 1
                failed_this_run.add(lead.id)
                continue

            # Envoi de l'email APRÈS la synchro, et jamais bloquant pour elle :
            # un échec SMTP laisse le lead en SYNCHRONISE_CRM (fiche Odoo créée,
            # email renvoyable depuis Odoo), il n'annule pas la synchronisation.
            if not settings.ODOO_SEND_EMAILS:
                continue
            if not lead.email:
                logger.warning(
                    "Lead %s sans adresse email prospect — envoi impossible", lead.siret
                )
                total_email_errors += 1
                continue
            try:
                await send_prospection_email(
                    odoo_lead_id, lead.objet_email, lead.contenu_email,
                    lead.email, email_from,
                )
                await update_lead_contacted(db, lead)
                total_emails_sent += 1
                logger.debug("Email envoyé à %s — lead %s CONTACTE", lead.email, lead.siret)
            except Exception as exc:
                logger.warning("Envoi email échoué pour %s : %s", lead.siret, exc)
                total_email_errors += 1

    logger.info(
        "Campagne %s — CRM : %d synchronisés, %d doublons rattachés, %d erreurs · "
        "emails : %d envoyés, %d erreurs",
        campaign.id, total_synced, total_duplicates, total_errors,
        total_emails_sent, total_email_errors,
    )
    return {
        "leads_synchronises": total_synced,
        "doublons_rattaches": total_duplicates,
        "leads_erreurs": total_errors,
        "emails_envoyes": total_emails_sent,
        "emails_erreurs": total_email_errors,
    }
