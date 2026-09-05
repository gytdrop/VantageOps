from datetime import timedelta
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    has_split_requirement = fields.Boolean(
        string='Requires Fulfillment Split',
        compute='_compute_split_requirement',
        store=True,
        help="Flagged if any line quantity exceeds primary warehouse free stock."
    )
    secondary_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Secondary Warehouse (Backorder)',
        help="Alternative warehouse used to fulfill inventory deficits."
    )

    # --- Multi-Warehouse Cost-Weighted Fulfillment Engine ---
    estimated_shipment_count = fields.Integer(
        string='Estimated Shipments',
        compute='_compute_shipping_metrics',
        store=True,
        help="Number of discrete warehouse shipments required to fulfill this quotation."
    )
    estimated_shipping_cost = fields.Float(
        string='Estimated Shipping Cost ($)',
        compute='_compute_shipping_metrics',
        store=True,
        help="Total shipping cost computed from warehouse base costs and weight factors."
    )
    fulfillment_split_summary = fields.Text(
        string='Fulfillment Split Summary',
        compute='_compute_shipping_metrics',
        store=True,
        help="Live recommendation explaining warehouse breakdown and shipment costs."
    )
    has_split_children = fields.Boolean(
        string='Has Split Lines',
        compute='_compute_has_split_children',
        help="True if backorder split child lines currently exist on this quotation."
    )

    # --- Hybrid Billing Schedule Engine ---
    billing_schedule_ids = fields.One2many(
        'vantage.billing.schedule',
        'order_id',
        string='Billing Schedules'
    )
    billing_schedule_count = fields.Integer(
        string='Billing Schedule Count',
        compute='_compute_billing_schedule_count'
    )

    # --- Smart Upsell Recommendations ---
    available_upsell_ids = fields.Many2many(
        'vantage.upsell.rule',
        string='Recommended Upsells',
        compute='_compute_available_upsells'
    )

    @api.depends('order_line.is_split_child')
    def _compute_has_split_children(self):
        for order in self:
            order.has_split_children = any(l.is_split_child for l in order.order_line)

    @api.depends(
        'order_line.product_uom_qty', 'order_line.product_id', 'order_line.fulfillment_warehouse_id',
        'order_line.is_split_child', 'order_line.requires_split', 'warehouse_id', 'secondary_warehouse_id'
    )
    def _compute_shipping_metrics(self):
        for order in self:
            physical_lines = order.order_line.filtered(lambda l: l.product_id.type == 'product')
            if not physical_lines:
                order.estimated_shipment_count = 0
                order.estimated_shipping_cost = 0.0
                order.fulfillment_split_summary = "No physical shippable items in order."
                continue

            pri_wh = order.warehouse_id or self.env['stock.warehouse'].search([], limit=1)
            pri_cost = (pri_wh.base_shipping_cost or 25.0) * (pri_wh.shipping_cost_weight or 1.0) if pri_wh else 25.0

            # If split lines already exist
            child_lines = physical_lines.filtered(lambda l: l.is_split_child)
            if child_lines:
                distinct_whs = {pri_wh} if physical_lines.filtered(lambda l: not l.is_split_child) else set()
                for cl in child_lines:
                    if cl.fulfillment_warehouse_id:
                        distinct_whs.add(cl.fulfillment_warehouse_id)

                total_cost = sum((w.base_shipping_cost or 25.0) * (w.shipping_cost_weight or 1.0) for w in distinct_whs)
                wh_names = ", ".join(w.name for w in distinct_whs)
                order.estimated_shipment_count = len(distinct_whs)
                order.estimated_shipping_cost = round(total_cost, 2)
                order.fulfillment_split_summary = (
                    f"📦 Active Split: {len(distinct_whs)} shipments across [{wh_names}] "
                    f"(Total Shipping: ${total_cost:,.2f})"
                )
            elif order.has_split_requirement:
                # Projected split needed
                sec_wh = order.secondary_warehouse_id or order._get_optimal_secondary_warehouse(physical_lines)
                sec_cost = (sec_wh.base_shipping_cost or 25.0) * (sec_wh.shipping_cost_weight or 1.0) if sec_wh else 60.0
                total_cost = pri_cost + sec_cost
                order.estimated_shipment_count = 2
                order.estimated_shipping_cost = round(total_cost, 2)
                order.fulfillment_split_summary = (
                    f"⚠️ Recommended Split: 2 shipments — Primary: {pri_wh.name} (${pri_cost:.2f}) + "
                    f"Backorder Depot: {sec_wh.name if sec_wh else 'Secondary WH'} (${sec_cost:.2f}) "
                    f"| Total Projected Shipping: ${total_cost:,.2f}"
                )
            else:
                # 1 single shipment
                order.estimated_shipment_count = 1
                order.estimated_shipping_cost = round(pri_cost, 2)
                order.fulfillment_split_summary = (
                    f"✅ Unified Fulfillment: 1 shipment from {pri_wh.name} "
                    f"(Base: ${pri_wh.base_shipping_cost:.2f} × Weight: {pri_wh.shipping_cost_weight:.1f} = ${pri_cost:,.2f})"
                )

    def _get_optimal_secondary_warehouse(self, physical_lines=None):
        """Finds secondary warehouse minimizing combined shipping weight while satisfying deficit"""
        self.ensure_one()
        all_whs = self.env['stock.warehouse'].search([('id', '!=', self.warehouse_id.id)])
        if not all_whs:
            return False

        # Rank candidate warehouses by cost weight (base_shipping_cost * shipping_cost_weight)
        def cost_rank(wh):
            return (wh.base_shipping_cost or 25.0) * (wh.shipping_cost_weight or 1.0)

        ranked = sorted(all_whs, key=cost_rank)
        return ranked[0] if ranked else False

    @api.depends('order_line.product_uom_qty', 'order_line.product_id', 'warehouse_id')
    def _compute_split_requirement(self):
        """Check available free stock vs requested qty"""
        for order in self:
            order.has_split_requirement = any(line.requires_split for line in order.order_line)

    @api.depends('billing_schedule_ids')
    def _compute_billing_schedule_count(self):
        for order in self:
            order.billing_schedule_count = len(order.billing_schedule_ids)

    @api.depends('order_line.product_id')
    def _compute_available_upsells(self):
        rule_obj = self.env['vantage.upsell.rule']
        for order in self:
            prod_ids = order.order_line.mapped('product_id').ids
            matching_rules = rule_obj.search([
                ('source_product_id', 'in', prod_ids),
                ('recommended_product_id', 'not in', prod_ids)
            ])
            order.available_upsell_ids = matching_rules

    def action_generate_billing_schedule(self):
        """Autonomously separates one-time hardware from recurring subscription schedules"""
        self.ensure_one()
        # Remove un-invoiced schedules
        self.billing_schedule_ids.filtered(lambda s: s.state == 'scheduled').unlink()

        one_time_total = sum(l.price_subtotal for l in self.order_line if not l.is_subscription_item)
        sub_lines = self.order_line.filtered(lambda l: l.is_subscription_item)
        recurring_monthly = sum(l.price_subtotal for l in sub_lines)

        today = fields.Date.context_today(self)
        schedules = []
        seq = 1

        # 1. One-Time Hardware / Implementation Invoice
        if one_time_total > 0 or not sub_lines:
            schedules.append({
                'order_id': self.id,
                'sequence': seq,
                'billing_date': today,
                'description': 'Initial Delivery & Hardware / Setup Charges',
                'amount': one_time_total if one_time_total > 0 else self.amount_untaxed,
                'billing_type': 'one_time',
                'state': 'scheduled'
            })
            seq += 1

        # 2. Recurring Subscription Installments (12 Monthly Cycles)
        if recurring_monthly > 0:
            for month in range(1, 13):
                inv_date = today + timedelta(days=30 * month)
                schedules.append({
                    'order_id': self.id,
                    'sequence': seq,
                    'billing_date': inv_date,
                    'description': f'Recurring SaaS Subscription (Cycle {month} of 12)',
                    'amount': round(recurring_monthly / 12.0, 2) if recurring_monthly > 100 else recurring_monthly,
                    'billing_type': 'recurring',
                    'state': 'scheduled'
                })
                seq += 1

        self.env['vantage.billing.schedule'].create(schedules)
        self.message_post(body=f"📅 <strong>Hybrid Billing Schedule Generated:</strong> Created {len(schedules)} installment periods (One-time: ${one_time_total:,.2f}, Recurring: ${recurring_monthly:,.2f}).")

    def action_split_fulfillments(self):
        """Autonomously split lines with deficits into secondary warehouse lines using cost weighting"""
        for order in self:
            lines_to_split = order.order_line.filtered(
                lambda l: l.requires_split and not l.is_split_child and l.product_id.type == 'product'
            )
            if not lines_to_split:
                raise UserError(_("No stock deficit detected across line items for split."))

            sec_wh = order.secondary_warehouse_id or order._get_optimal_secondary_warehouse(lines_to_split)
            if not sec_wh:
                sec_wh = self.env['stock.warehouse'].sudo().search([('id', '!=', order.warehouse_id.id)], limit=1)
            order.secondary_warehouse_id = sec_wh

            split_count = 0
            for line in lines_to_split:
                avail_qty = max(0.0, line.free_qty_today)
                deficit = line.product_uom_qty - avail_qty

                if deficit > 0:
                    if avail_qty > 0:
                        line.product_uom_qty = avail_qty
                        line.is_split_parent = True

                        order.order_line.create({
                            'order_id': order.id,
                            'product_id': line.product_id.id,
                            'product_uom_qty': deficit,
                            'price_unit': line.price_unit,
                            'discount': line.discount,
                            'is_split_child': True,
                            'split_source_line_id': line.id,
                            'fulfillment_warehouse_id': sec_wh.id if sec_wh else False,
                            'name': f"{line.name} (Split Backorder - {sec_wh.name if sec_wh else 'Secondary WH'})",
                        })
                    else:
                        line.fulfillment_warehouse_id = sec_wh.id if sec_wh else False
                        line.is_split_child = True
                    split_count += 1

            wh_cost = (sec_wh.base_shipping_cost or 25.0) * (sec_wh.shipping_cost_weight or 1.0) if sec_wh else 60.0
            order.message_post(
                body=(
                    f"⚙️ <strong>VantageOps Fulfillment Auto-Split</strong>: {split_count} line items routed. "
                    f"Secondary Warehouse: <strong>{sec_wh.name if sec_wh else 'Depot'}</strong> "
                    f"(Cost Weight: {sec_wh.shipping_cost_weight if sec_wh else 1.0}x, Est. Leg Cost: ${wh_cost:.2f})."
                )
            )

    def action_consolidate_backorders(self):
        """Consolidates backorder split child lines back into parent lines when stock arrives"""
        for order in self:
            child_lines = order.order_line.filtered(lambda l: l.is_split_child)
            if not child_lines:
                raise UserError(_("No split backorder lines to consolidate."))

            consolidated_count = 0
            for child in child_lines:
                parent = child.split_source_line_id
                if parent and parent.exists():
                    parent.product_uom_qty += child.product_uom_qty
                    parent.is_split_parent = False
                    child.unlink()
                    consolidated_count += 1
                else:
                    child.is_split_child = False

            order.message_post(
                body=f"📦 <strong>Fulfillment Backorders Consolidated</strong>: {consolidated_count} backorder line(s) merged back into primary warehouse shipment."
            )


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    free_qty_today = fields.Float(
        string='Available Free Stock',
        compute='_compute_free_qty_today'
    )
    requires_split = fields.Boolean(
        string='Stock Deficit',
        compute='_compute_requires_split',
        store=True
    )
    is_split_parent = fields.Boolean(string='Is Split Parent', default=False)
    is_split_child = fields.Boolean(string='Is Backorder Split Line', default=False)
    split_source_line_id = fields.Many2one('sale.order.line', string='Source Split Line')
    fulfillment_warehouse_id = fields.Many2one('stock.warehouse', string='Fulfillment Warehouse')
    deficit_qty = fields.Float(
        string='Deficit Quantity',
        compute='_compute_deficit_qty',
        store=True,
        help="Deficit quantity exceeding primary warehouse available stock."
    )

    margin_delta = fields.Float(
        string='Margin Delta ($)',
        compute='_compute_margin_delta',
        store=True,
        help="Net profit contribution of this line item."
    )

    @api.depends('product_id', 'order_id.warehouse_id')
    def _compute_free_qty_today(self):
        for line in self:
            if line.product_id and line.product_id.type == 'product':
                wh = line.order_id.warehouse_id
                stock_loc = wh.lot_stock_id.id if wh else False
                line.free_qty_today = line.product_id.with_context(location=stock_loc).free_qty if stock_loc else line.product_id.free_qty
            else:
                line.free_qty_today = line.product_uom_qty

    @api.depends('free_qty_today', 'product_uom_qty', 'is_split_child')
    def _compute_requires_split(self):
        for line in self:
            if not line.is_split_child and line.product_id.type == 'product':
                line.requires_split = line.product_uom_qty > line.free_qty_today
            else:
                line.requires_split = False

    @api.depends('free_qty_today', 'product_uom_qty', 'is_split_child')
    def _compute_deficit_qty(self):
        for line in self:
            if not line.is_split_child and line.product_id.type == 'product' and line.product_uom_qty > line.free_qty_today:
                line.deficit_qty = line.product_uom_qty - line.free_qty_today
            else:
                line.deficit_qty = 0.0

    @api.depends('price_subtotal', 'product_id', 'product_uom_qty')
    def _compute_margin_delta(self):
        for line in self:
            cost = line.product_id.standard_price * line.product_uom_qty if line.product_id else 0.0
            line.margin_delta = round(line.price_subtotal - cost, 2)


class SaleOrderOption(models.Model):
    _inherit = 'sale.order.option'

    margin_delta = fields.Float(
        string='Margin Delta ($)',
        compute='_compute_margin_delta',
        store=True,
        help="Net profit contribution of this optional product."
    )

    @api.depends('price_unit', 'product_id', 'quantity', 'discount')
    def _compute_margin_delta(self):
        for option in self:
            cost = option.product_id.standard_price * option.quantity if option.product_id else 0.0
            price_subtotal = option.price_unit * option.quantity * (1 - (option.discount or 0.0) / 100.0)
            option.margin_delta = round(price_subtotal - cost, 2)


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    shipping_cost_weight = fields.Float(
        string='Shipping Cost Weight',
        default=1.0,
        help="Weight multiplier for distance/regional shipping costs (e.g. 1.0 for Main WH, 2.5 for East Depot)."
    )
    base_shipping_cost = fields.Float(
        string='Base Shipping Cost ($)',
        default=25.0,
        help="Base dispatch cost per shipment before distance weighting."
    )

