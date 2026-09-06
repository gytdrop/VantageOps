from dateutil.relativedelta import relativedelta
from markupsafe import Markup

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from odoo.addons.vantage_core.models.vantage_config import CADENCE_SELECTION


class VantageProrationWizard(models.TransientModel):
    """Mid-cycle seat changes billed on exact calendar days.

    Adding 5 licences on the 18th of a 30-day cycle bills 5 × price × 13/30 — not a
    whole cycle and not nothing. Removing seats produces a negative adjustment (credit).
    """
    _name = 'vantage.proration.wizard'
    _description = 'VantageOps Mid-Cycle Subscription Proration'

    order_id = fields.Many2one(
        'sale.order', string='Quotation', required=True,
        default=lambda self: self.env.context.get('active_id')
    )
    line_id = fields.Many2one(
        'sale.order.line', string='Subscription Line', required=True,
        domain="[('order_id', '=', order_id), ('is_subscription_item', '=', True)]"
    )
    change_date = fields.Date(
        string='Change Effective Date', required=True, default=fields.Date.context_today
    )
    qty_delta = fields.Float(
        string='Quantity Change', required=True, default=1.0,
        help="Positive to add seats/licences, negative to remove them (produces a credit)."
    )
    apply_qty_change = fields.Boolean(
        string='Also Update the Order Line', default=True,
        help="Write the new quantity onto the subscription line as well as billing the adjustment."
    )
    reason = fields.Char(string='Reason')

    currency_id = fields.Many2one(related='order_id.currency_id', readonly=True)
    cadence = fields.Selection(CADENCE_SELECTION, string='Cadence', compute='_compute_proration')
    period_start = fields.Date(string='Cycle Start', compute='_compute_proration')
    period_end = fields.Date(string='Cycle End', compute='_compute_proration')
    period_days = fields.Integer(string='Days in Cycle', compute='_compute_proration')
    remaining_days = fields.Integer(string='Days Remaining', compute='_compute_proration')
    proration_factor = fields.Float(string='Proration Factor', digits=(12, 6), compute='_compute_proration')
    unit_period_price = fields.Monetary(
        string='Cycle Price per Unit', currency_field='currency_id', compute='_compute_proration'
    )
    prorated_amount = fields.Monetary(
        string='Prorated Adjustment', currency_field='currency_id', compute='_compute_proration'
    )
    proration_explanation = fields.Char(string='Calculation', compute='_compute_proration')

    @api.depends('line_id', 'change_date', 'qty_delta')
    def _compute_proration(self):
        for wizard in self:
            line = wizard.line_id
            if not line or not wizard.change_date:
                wizard.cadence = False
                wizard.period_start = wizard.period_end = False
                wizard.period_days = wizard.remaining_days = 0
                wizard.proration_factor = 0.0
                wizard.unit_period_price = wizard.prorated_amount = 0.0
                wizard.proration_explanation = _("Select a subscription line to preview the adjustment.")
                continue

            period_start, period_end = line._vantage_period_bounds(wizard.change_date)
            period_days = (period_end - period_start).days
            remaining_days = max(0, (period_end - max(wizard.change_date, period_start)).days)
            factor = (remaining_days / period_days) if period_days else 0.0

            qty = line.product_uom_qty or 1.0
            unit_price = line._vantage_period_amount() / qty if qty else 0.0
            amount = round(unit_price * wizard.qty_delta * factor, 2)

            wizard.cadence = line.billing_cadence
            wizard.period_start = period_start
            wizard.period_end = period_end - relativedelta(days=1)
            wizard.period_days = period_days
            wizard.remaining_days = remaining_days
            wizard.proration_factor = round(factor, 6)
            wizard.unit_period_price = round(unit_price, 2)
            wizard.prorated_amount = amount
            wizard.proration_explanation = _(
                "%(qty)g unit(s) × %(price).2f per cycle × %(days)s/%(total)s remaining days = %(amount).2f",
                qty=wizard.qty_delta, price=unit_price,
                days=remaining_days, total=period_days, amount=amount,
            )

    def action_apply_proration(self):
        self.ensure_one()
        line = self.line_id
        if not line:
            raise UserError(_("Select the subscription line to adjust."))
        if not self.qty_delta:
            raise UserError(_("Enter a non-zero quantity change."))

        service_start, service_end = line._vantage_service_window()
        if not (service_start <= self.change_date < service_end):
            raise UserError(_(
                "The change date must fall inside the contract window (%(start)s → %(end)s).",
                start=service_start, end=service_end - relativedelta(days=1),
            ))
        if self.apply_qty_change and (line.product_uom_qty + self.qty_delta) < 0:
            raise UserError(_("The quantity change would drive the line below zero units."))

        self.env['vantage.billing.schedule'].create({
            'order_id': self.order_id.id,
            'source_line_id': line.id,
            'sequence': 99,
            'billing_date': self.change_date,
            'description': _("Mid-cycle adjustment (%(delta)+g units) — %(product)s",
                             delta=self.qty_delta, product=line.product_id.display_name or line.name),
            'amount': self.prorated_amount,
            'billing_type': 'proration',
            'state': 'scheduled',
            'cadence': line.billing_cadence,
            'period_start': self.period_start,
            'period_end': self.period_end,
            'proration_factor': self.proration_factor,
            'is_prorated': True,
            'proration_note': self.proration_explanation,
        })

        if self.apply_qty_change:
            line.product_uom_qty += self.qty_delta

        self.order_id.message_post(
            body=Markup(_(
                "📐 <strong>Mid-Cycle Proration Applied</strong> on %(product)s.<br/>"
                "Effective %(date)s, cycle %(start)s → %(end)s.<br/>"
                "%(explanation)s<br/>%(reason)s",
                product=line.product_id.display_name or line.name,
                date=self.change_date, start=self.period_start, end=self.period_end,
                explanation=self.proration_explanation,
                reason=self.reason or '',
            )),
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )
        return {'type': 'ir.actions.act_window_close'}
