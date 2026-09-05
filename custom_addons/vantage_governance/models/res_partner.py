from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    customer_tier_id = fields.Many2one(
        'vantage.discount.tier',
        string='Vantage Customer Tier',
        tracking=True,
        ondelete='restrict',
        default=lambda self: self.env['vantage.discount.tier']._get_default_tier(),
        help="Determines the permissible discount ceiling before triggering approval workflows."
    )
    customer_tier_ceiling = fields.Float(
        related='customer_tier_id.discount_ceiling',
        string='Discount Ceiling (%)',
        readonly=True,
    )
