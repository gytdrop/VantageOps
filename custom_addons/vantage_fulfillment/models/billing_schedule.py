from odoo import models, fields, api

class VantageBillingSchedule(models.Model):
    _name = 'vantage.billing.schedule'
    _description = 'Hybrid Deal Billing Schedule'
    _order = 'billing_date asc, sequence asc'

    order_id = fields.Many2one('sale.order', string='Sale Order', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Seq', default=10)
    billing_date = fields.Date(string='Scheduled Invoice Date', required=True, default=fields.Date.context_today)
    description = fields.Char(string='Billing Description', required=True)
    amount = fields.Monetary(string='Period Amount', required=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='order_id.currency_id', store=True, readonly=True)
    billing_type = fields.Selection([
        ('one_time', 'One-Time Hardware / Setup'),
        ('recurring', 'Recurring SaaS / Subscription')
    ], string='Billing Category', default='recurring', required=True)
    state = fields.Selection([
        ('scheduled', 'Scheduled'),
        ('invoiced', 'Invoiced'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='scheduled', required=True)

    def action_mark_invoiced(self):
        for rec in self:
            rec.state = 'invoiced'
        return True
