# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class VantageBargainWizard(models.TransientModel):
    _name = 'vantage.bargain.wizard'
    _description = 'VantageOps Deal Negotiation & Bargain Pitch Wizard'

    order_id = fields.Many2one('sale.order', string='Quotation', required=True, default=lambda self: self.env.context.get('active_id'))
    current_discount = fields.Float(string='Current Avg Discount (%)', compute='_compute_current_metrics')
    current_risk_score = fields.Float(string='Current Risk Score', compute='_compute_current_metrics')
    negotiation_round = fields.Integer(string='Current Round', compute='_compute_current_metrics')
    max_rounds = fields.Integer(string='Max Permitted Rounds', compute='_compute_current_metrics')

    counter_discount = fields.Float(string='Proposed Counter Discount (%)', required=True, default=10.0)
    apply_to = fields.Selection([
        ('all', 'Order-Wide (All Quotation Lines)'),
        ('specific', 'Specific Product Line'),
    ], string='Application Scope', default='all', required=True)
    line_id = fields.Many2one('sale.order.line', string='Target Product Line', domain="[('order_id', '=', order_id)]")
    notes = fields.Text(string='Concession Notes / Proposal Pitch')

    @api.depends('order_id')
    def _compute_current_metrics(self):
        for wiz in self:
            order = wiz.order_id
            wiz.current_risk_score = order.blended_risk_score if order else 0.0
            wiz.negotiation_round = order.negotiation_rounds if order else 0
            wiz.max_rounds = order.max_negotiation_rounds if order else 3
            if order and order.order_line:
                discs = order.order_line.mapped('discount')
                wiz.current_discount = round(sum(discs) / len(discs), 2) if discs else 0.0
            else:
                wiz.current_discount = 0.0

    def action_apply_pitch(self):
        self.ensure_one()
        order = self.order_id
        if not order:
            raise UserError(_("No active quotation associated with this bargain pitch."))
        if not order.order_line:
            raise UserError(_("Cannot pitch a discount on an empty quotation. Please add at least one product line first."))

        target_line_id = self.line_id.id if self.apply_to == 'specific' and self.line_id else None
        order.action_customer_counter_offer(
            line_id=target_line_id,
            counter_discount=self.counter_discount,
            notes=self.notes or _("Commercial counter-offer pitched by sales admin.")
        )
        return {'type': 'ir.actions.act_window_close'}
