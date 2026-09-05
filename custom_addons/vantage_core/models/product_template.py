from odoo import models, fields

from .vantage_config import CADENCE_SELECTION


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    vantage_is_subscription = fields.Boolean(
        string='VantageOps Subscription Product',
        help="Explicitly mark this product as a recurring subscription. When left unchecked, "
             "VantageOps falls back to a name-based heuristic for backwards compatibility."
    )
    vantage_billing_cadence = fields.Selection(
        CADENCE_SELECTION,
        string='Billing Cadence',
        default='monthly',
        help="How often this subscription is invoiced. Drives the number of billing milestones "
             "generated on the sales order."
    )
    vantage_contract_months = fields.Integer(
        string='Contract Duration (Months)',
        default=0,
        help="Total committed contract length in months. Leave at 0 to inherit the company "
             "default configured in Sales Settings."
    )
    vantage_price_basis = fields.Selection([
        ('contract', 'Sales Price = Total Contract Value'),
        ('period', 'Sales Price = Amount per Billing Period'),
    ], string='Subscription Price Basis', default='contract',
        help="Tells the billing engine how to read the sales price: either the whole committed "
             "contract value (which gets divided across the cycles) or the price of a single cycle."
    )
