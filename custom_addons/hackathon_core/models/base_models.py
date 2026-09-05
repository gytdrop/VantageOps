from odoo import models, fields, api

class DealflowProduct(models.Model):
    _name = 'dealflow.product'
    _description = 'DealFlow Product'

    name = fields.Char(string='Product Name', required=True)
    category_type = fields.Selection([
        ('hardware', 'Hardware'),
        ('service', 'Service'),
        ('subscription', 'Subscription')
    ], string='Category Type', required=True, default='hardware')
    list_price = fields.Float(string='Sales Price', default=0.0)
    standard_price = fields.Float(string='Cost Price', default=0.0)
    max_discount = fields.Float(string='Max Default Discount (%)', default=10.0)
    active = fields.Boolean(string='Active', default=True)


class DealflowQuote(models.Model):
    _name = 'dealflow.quote'
    _description = 'DealFlow Quotation'
    _inherit = ['mail.thread', 'mail.activity.mixin'] if 'mail.thread' in dir(models) else []

    name = fields.Char(string='Quote Reference', required=True, default='New', copy=False)
    partner_name = fields.Char(string='Customer Name', required=True)
    partner_email = fields.Char(string='Customer Email')
    partner_tier = fields.Selection([
        ('bronze', 'Bronze (Up to 5%)'),
        ('silver', 'Silver (Up to 10%)'),
        ('gold', 'Gold (Up to 15%)')
    ], string='Customer Tier', default='bronze', required=True)
    user_id = fields.Many2one('res.users', string='Sales Rep', default=lambda self: self.env.user)
    date_order = fields.Datetime(string='Order Date', default=fields.Datetime.now)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('under_negotiation', 'Under Negotiation'),
        ('pending_manager', 'Pending Manager Approval'),
        ('pending_finance', 'Pending Finance Approval'),
        ('approved', 'Approved'),
        ('confirmed', 'Confirmed'),
        ('done', 'Fulfilled & Invoiced'),
        ('rejected', 'Rejected'),
        ('cancel', 'Cancelled')
    ], string='Status', default='draft', tracking=True)

    line_ids = fields.One2many('dealflow.quote.line', 'quote_id', string='Quote Lines')
    amount_untaxed = fields.Float(string='Untaxed Amount', compute='_compute_amounts', store=True)
    amount_discount = fields.Float(string='Total Discount Amount', compute='_compute_amounts', store=True)
    amount_total = fields.Float(string='Total Amount', compute='_compute_amounts', store=True)
    order_margin = fields.Float(string='Total Margin ($)', compute='_compute_amounts', store=True)
    order_margin_percent = fields.Float(string='Margin (%)', compute='_compute_amounts', store=True)
    notes = fields.Text(string='Terms & Notes')

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('dealflow.quote') or f"DFQ-{self.env['ir.sequence'].sudo().search_count([]) + 1001}"
        return super().create(vals)

    @api.depends('line_ids.price_subtotal', 'line_ids.margin', 'line_ids.price_unit', 'line_ids.quantity', 'line_ids.discount')
    def _compute_amounts(self):
        for record in self:
            total_untaxed = sum(line.price_subtotal for line in record.line_ids)
            gross_amount = sum(line.price_unit * line.quantity for line in record.line_ids)
            total_discount = gross_amount - total_untaxed
            total_margin = sum(line.margin for line in record.line_ids)
            margin_pct = (total_margin / total_untaxed * 100) if total_untaxed > 0 else 0.0

            record.amount_untaxed = total_untaxed
            record.amount_discount = total_discount
            record.amount_total = total_untaxed
            record.order_margin = total_margin
            record.order_margin_percent = margin_pct


class DealflowQuoteLine(models.Model):
    _name = 'dealflow.quote.line'
    _description = 'DealFlow Quotation Line'

    quote_id = fields.Many2one('dealflow.quote', string='Quotation', ondelete='cascade', required=True)
    product_id = fields.Many2one('dealflow.product', string='Product', required=True)
    category_type = fields.Selection(related='product_id.category_type', string='Category Type', store=True)
    quantity = fields.Float(string='Quantity', default=1.0)
    price_unit = fields.Float(string='Unit Price', default=0.0)
    cost_price = fields.Float(string='Unit Cost', default=0.0)
    discount = fields.Float(string='Discount (%)', default=0.0)
    price_subtotal = fields.Float(string='Subtotal', compute='_compute_line_subtotal', store=True)
    margin = fields.Float(string='Margin ($)', compute='_compute_line_subtotal', store=True)
    margin_percent = fields.Float(string='Margin (%)', compute='_compute_line_subtotal', store=True)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.price_unit = self.product_id.list_price
            self.cost_price = self.product_id.standard_price

    @api.depends('quantity', 'price_unit', 'cost_price', 'discount')
    def _compute_line_subtotal(self):
        for line in self:
            gross = line.quantity * line.price_unit
            discount_amount = gross * (line.discount / 100.0)
            subtotal = gross - discount_amount
            total_cost = line.quantity * line.cost_price
            margin = subtotal - total_cost
            margin_pct = (margin / subtotal * 100.0) if subtotal > 0 else 0.0

            line.price_subtotal = subtotal
            line.margin = margin
            line.margin_percent = margin_pct


# Backwards-compatibility shim for initial boilerplate hackathon.item
class HackathonBaseItem(models.Model):
    _name = 'hackathon.item'
    _description = 'Core Hackathon Entity'

    name = fields.Char(string='Item Name', required=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('done', 'Completed')
    ], default='draft', string='Status')
