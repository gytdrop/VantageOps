{
    'name': 'VantageOps Governance (Commercial Control)',
    'version': '17.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Approval Routing, Chatter Escalations & Portal Negotiation (Akthar)',
    'author': 'Akthar',
    'depends': ['vantage_core', 'portal', 'mail', 'vantage_fulfillment'],
    'data': [
        'security/ir.model.access.csv',
        'views/dashboard_views.xml',
        'views/governance_views.xml',
        'views/portal_templates.xml',
    ],
    'installable': True,
    'application': False,
}
