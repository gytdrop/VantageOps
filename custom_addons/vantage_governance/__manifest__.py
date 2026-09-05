{
    'name': 'VantageOps Governance (Commercial Control)',
    'version': '17.0.1.1.0',
    'category': 'Sales/Sales',
    'summary': 'Configurable Discount Tiers, Approval Routing, Chatter Escalations & Portal Negotiation',
    'author': 'gytdrop',
    'depends': ['vantage_core', 'portal', 'mail', 'vantage_fulfillment', 'sales_team'],
    'data': [
        'security/ir.model.access.csv',
        'data/discount_tier_data.xml',
        'views/discount_policy_views.xml',
        'views/res_config_settings_views.xml',
        'views/dashboard_views.xml',
        'views/governance_views.xml',
        'views/portal_templates.xml',
    ],
    'installable': True,
    'application': False,
}
