{
    'name': 'Hackathon Core',
    'version': '1.0',
    'category': 'Custom',
    'summary': 'Shared Base Models & Security Rules for Hackathon',
    'depends': ['base', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/base_views.xml',
    ],
    'installable': True,
    'application': True,
}
