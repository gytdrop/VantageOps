{
    'name': 'VantageOps Governance (Commercial Control)',
    'version': '17.0.1.1.0',
    'category': 'Sales/Sales',
    'summary': 'Configurable Discount Tiers, Approval Routing, Chatter Escalations & Portal Negotiation',
    'author': 'gytdrop',
    'depends': ['vantage_core', 'portal', 'mail', 'vantage_fulfillment', 'sales_team', 'bus'],
    'data': [
        'security/ir.model.access.csv',
        'data/discount_tier_data.xml',
        'views/discount_policy_views.xml',
        'views/res_config_settings_views.xml',
        'views/dashboard_views.xml',
        'views/governance_views.xml',
        'views/sale_order_views.xml',
        'views/portal_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'vantage_governance/static/src/js/backend_live_sync.js',
            'vantage_governance/static/src/scss/kanban_pipeline.scss',
            'vantage_governance/static/src/scss/kanban_stretch.scss',
        ],
        'web.assets_frontend': [
            'vantage_governance/static/src/js/portal_live_sync.js',
        ],
    },
    'installable': True,
    'application': False,
}
