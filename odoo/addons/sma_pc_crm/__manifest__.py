{
    "name": "SMA-PC ProspectAI — Intégration CRM",
    "version": "17.0.1.3.0",
    "summary": (
        "Champs custom sur crm.lead, webhooks retour (gagné/perdu/réponse email) "
        "et serveur mail sortant de dev pour la plateforme SMA-PC ProspectAI"
    ),
    "category": "CRM",
    "depends": ["crm"],
    "data": [
        "data/config_parameters.xml",
        "data/mail_server.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
