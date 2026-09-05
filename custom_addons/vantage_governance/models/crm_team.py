from odoo import models, fields


class CrmTeam(models.Model):
    _inherit = 'crm.team'

    vantage_max_negotiation_rounds = fields.Integer(
        string='Max Negotiation Rounds',
        default=0,
        help="Counter-offer rounds this sales team may run before the circuit breaker locks "
             "the deal. Leave at 0 to inherit the customer tier or the global Sales Settings value."
    )
