{
    'name': 'VantageOps Fulfillment (Operational Execution)',
    'version': '17.0.1.1.0',
    'category': 'Inventory/Delivery',
    'summary': 'N-Way Depot Allocation, Cadence-Aware Subscription Billing & Live Upsell Engine',
    'author': 'gytdrop',
    'depends': ['vantage_core', 'sale_stock', 'sale_management'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'views/proration_wizard_views.xml',
        'views/fulfillment_views.xml',
    ],
    'installable': True,
    'application': False,
}
