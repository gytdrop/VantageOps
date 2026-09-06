from markupsafe import Markup

from odoo import models, fields, api

class VantageUpsellRule(models.Model):
    _name = 'vantage.upsell.rule'
    _description = 'VantageOps Smart Upsell Rule'

    name = fields.Char(string='Rule Name', required=True)
    source_product_id = fields.Many2one('product.product', string='Trigger Product', required=True,
                                        help="When this product is present in quotation, recommend upsell.")
    recommended_product_id = fields.Many2one('product.product', string='Recommended Upsell Product', required=True)
    margin_contribution = fields.Float(string='Estimated Profit Delta ($)', compute='_compute_margin_contribution', store=True)
    promoted_tag = fields.Char(string='Badge Tag', default='High Margin Pairing')

    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id)

    @api.depends('recommended_product_id', 'recommended_product_id.list_price', 'recommended_product_id.standard_price')
    def _compute_margin_contribution(self):
        for rule in self:
            if rule.recommended_product_id:
                rule.margin_contribution = round(rule.recommended_product_id.list_price - rule.recommended_product_id.standard_price, 2)
            else:
                rule.margin_contribution = 0.0

    def action_apply_upsell(self):
        """Add recommended product directly to the active sale order quotation"""
        self.ensure_one()
        order_id = self.env.context.get('active_id')
        if order_id:
            order = self.env['sale.order'].browse(order_id)
            if order.exists() and order.state in ('draft', 'sent'):
                order.order_line.create({
                    'order_id': order.id,
                    'product_id': self.recommended_product_id.id,
                    'product_uom_qty': 1.0,
                    'price_unit': self.recommended_product_id.list_price,
                    'name': f"[Upsell] {self.recommended_product_id.display_name}",
                })
                order.message_post(
                    body=Markup(
                        f"✨ <strong>Smart Upsell Applied:</strong> Added {self.recommended_product_id.display_name} "
                        f"(+${self.margin_contribution:,.2f} profit impact)."
                    ),
                    message_type='comment',
                    subtype_xmlid='mail.mt_note',
                )
                return {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                }
