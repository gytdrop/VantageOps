from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    blended_risk_score = fields.Float(
        string='Blended Risk Score',
        compute='_compute_vantage_risk',
        store=True,
        tracking=True,
        help="Order-wide penalty calculated from line-item discount deviations."
    )
    risk_approval_state = fields.Selection([
        ('draft', 'Draft / Clean'),
        ('pending_approval', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected')
    ], string='Risk Approval State', default='draft', tracking=True)

    is_recurring_hybrid = fields.Boolean(
        string='Is Hybrid Deal',
        compute='_compute_is_recurring_hybrid',
        store=True,
        help="Flag indicating mixed one-time products and recurring subscription lines."
    )

    @api.depends('order_line.discount', 'order_line.price_subtotal', 'order_line.product_uom_qty')
    def _compute_vantage_risk(self):
        """Baseline risk model used when the governance layer is not installed.

        The ceiling and the scoring weights come from Sales Settings; `vantage_governance`
        overrides this with the per-tier / per-product-category variant.
        """
        cfg = self.env['vantage.config']
        ceiling = cfg.get_float('default_discount_ceiling', 10.0)
        breach_weight = cfg.get_float('breach_weight', 0.6)
        margin_loss_weight = cfg.get_float('margin_loss_weight', 0.4)
        trigger = cfg.get_float('risk_trigger_threshold', 0.0)

        for order in self:
            worst_breach = 0.0
            total_discount_val = 0.0
            total_gross_val = 0.0

            for line in order.order_line:
                gross = line.price_unit * line.product_uom_qty
                discount_amt = gross * (line.discount / 100.0)
                total_gross_val += gross
                total_discount_val += discount_amt

                if line.discount > ceiling:
                    worst_breach = max(worst_breach, line.discount - ceiling)

            margin_loss_pct = (total_discount_val / total_gross_val * 100.0) if total_gross_val > 0 else 0.0
            score = round((worst_breach * breach_weight) + (margin_loss_pct * margin_loss_weight), 2)
            order.blended_risk_score = score

            if order.risk_approval_state not in ('approved', 'rejected'):
                if score > trigger:
                    order.risk_approval_state = 'pending_approval'
                else:
                    order.risk_approval_state = 'draft'

    @api.depends('order_line.product_id')
    def _compute_is_recurring_hybrid(self):
        for order in self:
            has_subscription = any(line.is_subscription_item for line in order.order_line)
            has_standard = any(not line.is_subscription_item for line in order.order_line)
            order.is_recurring_hybrid = has_subscription and has_standard


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    is_subscription_item = fields.Boolean(
        string='Subscription Line',
        compute='_compute_is_subscription_item',
        store=True
    )
    line_risk_score = fields.Float(
        string='Line Risk Penalty',
        compute='_compute_line_risk',
        store=True
    )

    @api.depends('product_id', 'product_id.vantage_is_subscription')
    def _compute_is_subscription_item(self):
        for line in self:
            product = line.product_id
            if not product:
                line.is_subscription_item = False
                continue
            if product.vantage_is_subscription:
                line.is_subscription_item = True
                continue
            # Legacy heuristic kept so pre-existing catalogues keep working untouched.
            name = (product.name or '').lower()
            line.is_subscription_item = bool(
                getattr(product, 'recurring_invoice', False) or
                'subscription' in name or 'recurring' in name or
                'annual' in name or 'monthly' in name or 'license' in name
            )

    @api.depends('discount')
    def _compute_line_risk(self):
        ceiling = self.env['vantage.config'].get_float('default_discount_ceiling', 10.0)
        for line in self:
            line.line_risk_score = max(0.0, line.discount - ceiling)
