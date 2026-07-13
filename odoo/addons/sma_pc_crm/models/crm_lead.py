import json
import logging
from functools import partial

import requests

from odoo import fields, models

_logger = logging.getLogger(__name__)

_WEBHOOK_TIMEOUT = 5


def _send_webhook(url, secret, payload):
    """Exécuté en post-commit : les erreurs sont loguées, jamais remontées —
    un backend SMA-PC injoignable ne doit pas casser une opération CRM Odoo."""
    try:
        headers = {"Content-Type": "application/json"}
        if secret:
            headers["X-SMA-Webhook-Secret"] = secret
        response = requests.post(
            url, data=json.dumps(payload), headers=headers, timeout=_WEBHOOK_TIMEOUT
        )
        if response.status_code != 200:
            _logger.warning(
                "Webhook SMA-PC %s : HTTP %s — %s",
                payload.get("event"), response.status_code, response.text[:200],
            )
    except Exception:
        _logger.exception("Webhook SMA-PC %s : envoi échoué", payload.get("event"))


class CrmLead(models.Model):
    _inherit = "crm.lead"

    x_sma_pc_id = fields.Char(string="ID SMA-PC", index=True, copy=False)
    x_score_ia = fields.Float(string="Score IA")
    x_label_ia = fields.Char(string="Label IA")
    x_sector = fields.Char(string="Secteur (NAF)")

    x_siret = fields.Char(string="SIRET")
    x_taille_entreprise = fields.Char(string="Tranche effectif (code INSEE)")
    x_date_creation_entreprise = fields.Date(string="Date de création entreprise")

    x_ca = fields.Integer(string="Chiffre d'affaires (€)")
    x_resultat_net = fields.Integer(string="Résultat net (€)")

    # ── Boucle retour vers SMA-PC (webhooks sortants, dossier §13.5.5) ────────

    def _sma_pc_notify(self, event):
        """Programme l'envoi d'un webhook vers le backend SMA-PC APRÈS commit :
        si la transaction Odoo est annulée (rollback), rien n'est envoyé, donc
        pas de faux événement côté SMA-PC. Ne concerne que les leads créés par
        l'Agent CRM (x_sma_pc_id renseigné)."""
        leads = self.filtered("x_sma_pc_id")
        if not leads:
            return

        get_param = self.env["ir.config_parameter"].sudo().get_param
        url = get_param("sma_pc.webhook_url")
        secret = get_param("sma_pc.webhook_secret")
        if not url:
            return

        for lead in leads:
            payload = {
                "event": event,
                "odoo_lead_id": lead.id,
                "x_sma_pc_id": lead.x_sma_pc_id,
            }
            self.env.cr.postcommit.add(partial(_send_webhook, url, secret, payload))

    def write(self, vals):
        # États AVANT écriture, pour ne notifier que les vraies transitions
        # (pas les réécritures du même état, ex. retry de l'Agent CRM).
        won_before = {lead.id: lead.stage_id.is_won for lead in self}
        active_before = {lead.id: lead.active for lead in self}

        result = super().write(vals)

        if "stage_id" in vals:
            newly_won = self.filtered(
                lambda lead: lead.stage_id.is_won and not won_before.get(lead.id)
            )
            newly_won._sma_pc_notify("lead.won")

        # action_set_lost archive le lead (active=False) : c'est le marqueur
        # "perdu" d'Odoo — il n'y a pas d'étape "Lost" dans le pipeline.
        if vals.get("active") is False:
            newly_lost = self.filtered(
                lambda lead: active_before.get(lead.id) and not lead.active
            )
            newly_lost._sma_pc_notify("lead.lost")

        return result

    def message_post(self, **kwargs):
        message = super().message_post(**kwargs)
        # message_type == 'email' : message ENTRANT via la passerelle mail
        # d'Odoo (réponse du prospect). Les messages rédigés dans Odoo sont des
        # 'comment', et l'historisation faite par l'Agent CRM passe en
        # 'notification' (défaut de message_post) — aucun des deux ne déclenche.
        if kwargs.get("message_type") == "email":
            self._sma_pc_notify("message.received")
        return message
