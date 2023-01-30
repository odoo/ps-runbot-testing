# -*- coding: utf-8 -*-
{
    'name': "Runbot record testing",
    'description': """
    Register any actions set in the interface to generate automated tests by a functional teams
    """,
    'category': '',
    'version': '0.1',
    'license': 'OEEL-1',

    'depends': [
        'base',
        'web',
    ],

    'data': [
        'security/ir.model.access.csv',
        'views/record.xml',
        'wizards/test_start.xml',
        'wizards/caught_error.xml',
        'templates/templates.xml',
    ],
    'demo': [
    ],
    'qweb': [
        'static/src/xml/template.xml'
    ],
    'auto_install' : False,
}
