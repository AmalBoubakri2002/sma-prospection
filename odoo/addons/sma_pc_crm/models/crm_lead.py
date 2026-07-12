from odoo import fields, models


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
