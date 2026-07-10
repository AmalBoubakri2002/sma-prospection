from odoo import fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    # x_sma_pc_id : clé d'idempotence utilisée par l'Agent CRM (SMA-PC ProspectAI)
    # pour retrouver un lead déjà synchronisé et faire un write() plutôt qu'un
    # create() lors d'une relance de campagne. Correspond à Lead.id (UUID) côté SMA-PC.
    x_sma_pc_id = fields.Char(string="ID SMA-PC", index=True, copy=False)
    x_score_ia = fields.Float(string="Score IA")
    # Valeurs réelles produites par l'Agent Scoring : CHAUD / TIEDE / FROID / HORS_CIBLE
    # (pas de Selection figée : la taxonomie de labels a déjà évolué une fois).
    x_label_ia = fields.Char(string="Label IA")
    x_sector = fields.Char(string="Secteur (NAF)")
