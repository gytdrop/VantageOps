from odoo import models, fields, api, _

class VantageSalesDashboard(models.Model):
    _name = 'vantage.sales.dashboard'
    _description = 'VantageOps Executive Sales Dashboard'

    name = fields.Char(string='Dashboard Title', default='VantageOps Executive Sales Cockpit')
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id)

    # --- 1. DEAL METRICS ---
    total_deal_count = fields.Integer(string='Total Deals', compute='_compute_metrics')
    total_pipeline_val = fields.Monetary(string='Total Pipeline Value', currency_field='currency_id', compute='_compute_metrics')
    avg_deal_val = fields.Monetary(string='Avg Deal Value', currency_field='currency_id', compute='_compute_metrics')
    high_risk_deal_count = fields.Integer(string='High-Risk Deals', compute='_compute_metrics')

    # --- 2. HEALTH METRICS ---
    healthy_deal_count = fields.Integer(string='Healthy Deals', compute='_compute_metrics')
    stalled_deal_count = fields.Integer(string='Stalled Deals (>3 Days)', compute='_compute_metrics')
    margin_bleed_count = fields.Integer(string='Critical Margin Bleed', compute='_compute_metrics')

    # --- 3. APPROVALS METRICS ---
    pending_manager_count = fields.Integer(string='Pending Manager Approval', compute='_compute_metrics')
    pending_finance_count = fields.Integer(string='Pending Finance Approval', compute='_compute_metrics')
    total_pending_approvals = fields.Integer(string='Total Pending Approvals', compute='_compute_metrics')
    approved_deal_count = fields.Integer(string='Approved Deals', compute='_compute_metrics')
    rejected_deal_count = fields.Integer(string='Rejected Deals', compute='_compute_metrics')

    # --- 4. QUOTATIONS METRICS ---
    draft_quotes_count = fields.Integer(string='Draft Quotations', compute='_compute_metrics')
    sent_quotes_count = fields.Integer(string='Sent Quotations', compute='_compute_metrics')
    confirmed_orders_count = fields.Integer(string='Confirmed Sales Orders', compute='_compute_metrics')

    # --- 5. SUBSCRIPTION & HYBRID METRICS ---
    hybrid_deal_count = fields.Integer(string='Hybrid Contracts', compute='_compute_metrics')
    total_billing_schedules = fields.Integer(string='Billing Milestones', compute='_compute_metrics')
    scheduled_recurring_val = fields.Monetary(string='Scheduled MRR Pipeline', currency_field='currency_id', compute='_compute_metrics')
    invoiced_recurring_val = fields.Monetary(string='Realized Revenue', currency_field='currency_id', compute='_compute_metrics')

    # --- 6. FULFILLMENT & LOGISTICS METRICS ---
    split_deficit_count = fields.Integer(string='Orders with Stock Deficit', compute='_compute_metrics')
    forked_backorders_count = fields.Integer(string='Forked Regional Backorders', compute='_compute_metrics')

    # --- RECENT ACTIVITY ---
    recent_activity_html = fields.Html(string='Recent Activity', compute='_compute_metrics')

    def _compute_metrics(self):
        order_obj = self.env['sale.order']
        line_obj = self.env['sale.order.line']
        sched_obj = self.env['vantage.billing.schedule'] if 'vantage.billing.schedule' in self.env else None
        msg_obj = self.env['mail.message']

        for rec in self:
            all_orders = order_obj.search([])
            rec.total_deal_count = len(all_orders)
            rec.total_pipeline_val = sum(all_orders.mapped('amount_total'))
            rec.avg_deal_val = round(rec.total_pipeline_val / rec.total_deal_count, 2) if rec.total_deal_count else 0.0
            rec.high_risk_deal_count = len(all_orders.filtered(lambda o: o.blended_risk_score > 0))

            # Health
            rec.healthy_deal_count = len(all_orders.filtered(lambda o: o.deal_health == 'healthy'))
            rec.stalled_deal_count = len(all_orders.filtered(lambda o: o.deal_health == 'stalled'))
            rec.margin_bleed_count = len(all_orders.filtered(lambda o: o.deal_health == 'margin_bleed'))

            # Approvals
            rec.pending_manager_count = len(all_orders.filtered(lambda o: o.risk_approval_state in ('pending_approval', 'pending_manager')))
            rec.pending_finance_count = len(all_orders.filtered(lambda o: o.risk_approval_state == 'pending_finance'))
            rec.total_pending_approvals = rec.pending_manager_count + rec.pending_finance_count
            rec.approved_deal_count = len(all_orders.filtered(lambda o: o.risk_approval_state == 'approved'))
            rec.rejected_deal_count = len(all_orders.filtered(lambda o: o.risk_approval_state == 'rejected'))

            # Quotations
            rec.draft_quotes_count = len(all_orders.filtered(lambda o: o.state == 'draft'))
            rec.sent_quotes_count = len(all_orders.filtered(lambda o: o.state == 'sent'))
            rec.confirmed_orders_count = len(all_orders.filtered(lambda o: o.state == 'sale'))

            # Subscriptions / Hybrid
            rec.hybrid_deal_count = len(all_orders.filtered(lambda o: o.is_recurring_hybrid))
            if sched_obj:
                all_schedules = sched_obj.search([])
                rec.total_billing_schedules = len(all_schedules)
                rec.scheduled_recurring_val = sum(all_schedules.filtered(lambda s: s.state == 'scheduled').mapped('amount'))
                rec.invoiced_recurring_val = sum(all_schedules.filtered(lambda s: s.state == 'invoiced').mapped('amount'))
            else:
                rec.total_billing_schedules = 0
                rec.scheduled_recurring_val = 0.0
                rec.invoiced_recurring_val = 0.0

            # Fulfillment
            rec.split_deficit_count = len(all_orders.filtered(lambda o: o.has_split_requirement))
            rec.forked_backorders_count = line_obj.search_count([('is_split_child', '=', True)])

            # Recent Activity HTML
            recent_msgs = msg_obj.search([('model', '=', 'sale.order'), ('message_type', '!=', 'user_notification')], limit=5, order='id desc')
            
            html = '<ul style="list-style-type: none; padding-left: 0; margin: 0;">'
            for m in recent_msgs:
                order = order_obj.browse(m.res_id)
                # Strip HTML tags from message body
                import re
                clean_body = re.sub(r'<[^>]+>', '', m.body or '')
                text = f"{order.name} - {clean_body}"
                if len(text) > 80:
                    text = text[:77] + '...'
                html += f'<li style="margin-bottom: 8px;">- {text}</li>'
            
            if not recent_msgs:
                html += '<li>- No recent activity found</li>'
                
            html += '</ul>'
            rec.recent_activity_html = html

    def action_refresh(self):
        """Recompute metrics"""
        self.ensure_one()
        self._compute_metrics()
        return True

    def action_new_quotation(self):
        return {
            'name': _('New Quotation'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_approvals(self):
        return self.action_view_pending_approvals()

    def action_view_all_deals(self):
        return {
            'name': _('Deal Pipeline'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'tree,kanban,form',
            'target': 'current',
        }

    def action_view_margin_bleed(self):
        return {
            'name': _('Critical Margin Bleed Deals'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'tree,kanban,form',
            'domain': [('deal_health', '=', 'margin_bleed')],
            'target': 'current',
        }

    def action_view_stalled(self):
        return {
            'name': _('Stalled Quotes (>3 Days Inactive)'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'tree,kanban,form',
            'domain': [('deal_health', '=', 'stalled')],
            'target': 'current',
        }

    def action_view_pending_approvals(self):
        return {
            'name': _('Deals Awaiting Commercial Sign-off'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'tree,kanban,form',
            'domain': [('risk_approval_state', 'in', ['pending_approval', 'pending_manager', 'pending_finance'])],
            'target': 'current',
        }

    def action_view_quotations(self):
        return {
            'name': _('Active Quotations (Draft & Sent)'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'tree,kanban,form',
            'domain': [('state', 'in', ['draft', 'sent'])],
            'target': 'current',
        }

    def action_view_confirmed_orders(self):
        return {
            'name': _('Confirmed Sales Orders'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'tree,kanban,form',
            'domain': [('state', '=', 'sale')],
            'target': 'current',
        }

    def action_view_subscriptions(self):
        return {
            'name': _('Hybrid Subscription Deals'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'tree,kanban,form',
            'domain': [('is_recurring_hybrid', '=', True)],
            'target': 'current',
        }

    def action_view_billing_schedules(self):
        return {
            'name': _('Hybrid Billing Installments'),
            'type': 'ir.actions.act_window',
            'res_model': 'vantage.billing.schedule',
            'view_mode': 'tree,form',
            'target': 'current',
        }

    def action_view_fulfillment_deficits(self):
        return {
            'name': _('Orders with Inventory Deficit'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'tree,kanban,form',
            'domain': [('has_split_requirement', '=', True)],
            'target': 'current',
        }

    def action_view_forked_backorders(self):
        return {
            'name': _('Forked Regional Backorder Lines'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order.line',
            'view_mode': 'tree,form',
            'domain': [('is_split_child', '=', True)],
            'target': 'current',
        }

    def action_load_turnkey_seed_data(self):
        """1-Click Turnkey Seed Data Generator for DealFlow360 Live Demo (Section 8)"""
        partner_obj = self.env['res.partner'].sudo()
        warehouse_obj = self.env['stock.warehouse'].sudo()
        product_obj = self.env['product.product'].sudo()
        quant_obj = self.env['stock.quant'].sudo()
        upsell_obj = self.env['vantage.upsell.rule'].sudo() if 'vantage.upsell.rule' in self.env else None

        # 1. Seed Dedicated Customer Tiers
        partners_data = [
            ('Acme Corp (Bronze Tier)', 'bronze', 'acme_bronze@dealflow360.demo'),
            ('Beta Industries (Silver Tier)', 'silver', 'beta_silver@dealflow360.demo'),
            ('Cyberdyne Systems (Gold VIP)', 'gold', 'cyberdyne_gold@dealflow360.demo'),
        ]
        for name, tier, email in partners_data:
            p = partner_obj.search([('name', '=', name)], limit=1)
            if not p:
                partner_obj.create({
                    'name': name,
                    'customer_tier': tier,
                    'email': email,
                    'customer_rank': 1,
                })
            else:
                p.write({'customer_tier': tier})

        # Auto-classify existing standard demo partners so reps can pick any contact
        existing_map = {
            'Azure Interior': 'gold',
            'Deco Addict': 'silver',
            'Gemini Furniture': 'bronze',
            'Ready Mat': 'bronze',
            'The Jackson Group': 'silver',
            'Lumber Inc': 'gold',
            'Test Gold VIP Client': 'gold',
            'Test Bronze Client': 'bronze',
        }
        for pname, tier in existing_map.items():
            ep = partner_obj.search([('name', 'ilike', pname)], limit=1)
            if ep:
                ep.write({'customer_tier': tier})

        # 2. Seed Warehouses & Cost Weights
        main_wh = warehouse_obj.search([('code', '=', 'MAIN')], limit=1)
        if not main_wh:
            wh_default = warehouse_obj.search([], limit=1)
            if wh_default:
                wh_default.write({
                    'name': 'Main Warehouse',
                    'code': 'MAIN',
                    'shipping_cost_weight': 1.0,
                    'base_shipping_cost': 25.0,
                })
                main_wh = wh_default
            else:
                main_wh = warehouse_obj.create({
                    'name': 'Main Warehouse',
                    'code': 'MAIN',
                    'shipping_cost_weight': 1.0,
                    'base_shipping_cost': 25.0,
                })
        else:
            main_wh.write({'name': 'Main Warehouse', 'shipping_cost_weight': 1.0, 'base_shipping_cost': 25.0})

        east_wh = warehouse_obj.search([('code', '=', 'EAST')], limit=1)
        if not east_wh:
            east_wh = warehouse_obj.search([('name', 'ilike', 'Chicago')], limit=1)
            if east_wh:
                east_wh.write({
                    'name': 'East Depot',
                    'code': 'EAST',
                    'shipping_cost_weight': 2.5,
                    'base_shipping_cost': 60.0,
                })
            else:
                east_wh = warehouse_obj.create({
                    'name': 'East Depot',
                    'code': 'EAST',
                    'shipping_cost_weight': 2.5,
                    'base_shipping_cost': 60.0,
                })
        else:
            east_wh.write({'name': 'East Depot', 'shipping_cost_weight': 2.5, 'base_shipping_cost': 60.0})

        # 3. Seed Demo Products
        # Hardware: DealFlow Enterprise Server (Storable)
        server_prod = product_obj.search([('name', '=', 'DealFlow Enterprise Server')], limit=1)
        if not server_prod:
            server_prod = product_obj.create({
                'name': 'DealFlow Enterprise Server',
                'type': 'product',
                'list_price': 2500.0,
                'standard_price': 1500.0,
                'default_code': 'DF-SRV-01',
            })
        else:
            server_prod.write({'list_price': 2500.0, 'standard_price': 1500.0, 'type': 'product'})

        # Service: Enterprise Setup & Deployment
        setup_prod = product_obj.search([('name', '=', 'Enterprise Setup & Deployment')], limit=1)
        if not setup_prod:
            setup_prod = product_obj.create({
                'name': 'Enterprise Setup & Deployment',
                'type': 'service',
                'list_price': 1200.0,
                'standard_price': 800.0,
                'default_code': 'DF-SRV-SET',
            })

        # Subscription: DealFlow360 SaaS License
        sub_prod = product_obj.search([('name', '=', 'DealFlow360 SaaS Annual License')], limit=1)
        if not sub_prod:
            sub_prod = product_obj.create({
                'name': 'DealFlow360 SaaS Annual License',
                'type': 'service',
                'list_price': 600.0,
                'standard_price': 50.0,
                'default_code': 'DF-SAAS-ANN',
            })

        # Upsell Option: 24/7 Mission-Critical SLA Warranty
        sla_prod = product_obj.search([('name', '=', '24/7 Mission-Critical SLA Warranty')], limit=1)
        if not sla_prod:
            sla_prod = product_obj.create({
                'name': '24/7 Mission-Critical SLA Warranty',
                'type': 'service',
                'list_price': 450.0,
                'standard_price': 100.0,
                'default_code': 'DF-SLA-247',
            })

        # 4. Seed Stock Quants for Server Product (5 at Main WH, 15 at East Depot)
        main_loc = main_wh.lot_stock_id
        east_loc = east_wh.lot_stock_id
        quant_mode = self.env['stock.quant'].with_context(inventory_mode=True).sudo()
        if main_loc and server_prod:
            curr_main = server_prod.with_context(location=main_loc.id).free_qty
            if curr_main != 5.0:
                q_main = quant_mode.search([('product_id', '=', server_prod.id), ('location_id', '=', main_loc.id)], limit=1)
                if not q_main:
                    q_main = quant_mode.create({
                        'product_id': server_prod.id,
                        'location_id': main_loc.id,
                        'inventory_quantity': 5.0,
                    })
                else:
                    q_main.inventory_quantity = 5.0
                q_main.action_apply_inventory()

        if east_loc and server_prod:
            curr_east = server_prod.with_context(location=east_loc.id).free_qty
            if curr_east != 15.0:
                q_east = quant_mode.search([('product_id', '=', server_prod.id), ('location_id', '=', east_loc.id)], limit=1)
                if not q_east:
                    q_east = quant_mode.create({
                        'product_id': server_prod.id,
                        'location_id': east_loc.id,
                        'inventory_quantity': 15.0,
                    })
                else:
                    q_east.inventory_quantity = 15.0
                q_east.action_apply_inventory()

        # 5. Seed Upsell Pairing Rule
        if upsell_obj and server_prod and sla_prod:
            rule = upsell_obj.search([('source_product_id', '=', server_prod.id), ('recommended_product_id', '=', sla_prod.id)], limit=1)
            if not rule:
                upsell_obj.create({
                    'name': 'Server -> 24/7 SLA Warranty Upsell',
                    'source_product_id': server_prod.id,
                    'recommended_product_id': sla_prod.id,
                    'margin_contribution': 350.0,
                    'promoted_tag': 'Hot Deal (78% Margin)',
                })

        # 6. Seed Quotation Template Bundle
        if 'sale.order.template' in self.env and server_prod and setup_prod and sub_prod:
            tmpl_obj = self.env['sale.order.template'].sudo()
            bundle = tmpl_obj.search([('name', '=', 'DealFlow360 Enterprise Hybrid Bundle')], limit=1)
            if not bundle:
                tmpl_obj.create({
                    'name': 'DealFlow360 Enterprise Hybrid Bundle',
                    'sale_order_template_line_ids': [
                        (0, 0, {'product_id': server_prod.id, 'product_uom_qty': 10.0, 'name': server_prod.name}),
                        (0, 0, {'product_id': setup_prod.id, 'product_uom_qty': 1.0, 'name': setup_prod.name}),
                        (0, 0, {'product_id': sub_prod.id, 'product_uom_qty': 1.0, 'name': sub_prod.name}),
                    ],
                })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('⚡ Turnkey Seed Data Ready!'),
                'message': _(
                    'Pre-seeded Bronze/Silver/Gold accounts, Main Warehouse (5 units stock, $25 base) '
                    '& East Depot (15 units stock, $60 base), Demo Products, and Smart Upsell Rules.'
                ),
                'sticky': False,
                'type': 'success',
                'next': {'type': 'ir.actions.client', 'tag': 'reload'}
            }
        }

