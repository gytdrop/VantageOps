{
    'name': 'VantageOps Core',
    'version': '17.0.1.1.0',
    'category': 'Sales/Sales',
    'summary': 'Shared Foundation: Configurable Policy Accessor, Blended Risk Score & Deal Digital Twin',
    'author': 'gytdrop',
    'depends': ['base', 'sale', 'sale_management', 'mail', 'stock', 'account'],
    'data': [
        'views/menus.xml',
        'views/vantage_core_views.xml',
        'views/dashboard_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'vantage_core/static/src/scss/vantage_dashboard.scss',
        ],
    },
    'installable': True,
    'application': True,
}
