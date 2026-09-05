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
    stalled_deal_count = fields.Integer(string='Stalled Deals', compute='_compute_metrics')
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
            'name': _('Stalled Quotes (Inactive Beyond Threshold)'),
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

        # 1. Seed Dedicated Customer Tiers (resolved against the configurable tier policy)
        tier_obj = self.env['vantage.discount.tier'].sudo()
        tiers_by_code = {t.code: t for t in tier_obj.search([])}

        partners_data = [
            ('Acme Corp (Bronze Tier)', 'bronze', 'acme_bronze@dealflow360.demo'),
            ('Beta Industries (Silver Tier)', 'silver', 'beta_silver@dealflow360.demo'),
            ('Cyberdyne Systems (Gold VIP)', 'gold', 'cyberdyne_gold@dealflow360.demo'),
        ]
        for name, tier_code, email in partners_data:
            tier = tiers_by_code.get(tier_code)
            if not tier:
                continue
            p = partner_obj.search([('name', '=', name)], limit=1)
            if not p:
                partner_obj.create({
                    'name': name,
                    'customer_tier_id': tier.id,
                    'email': email,
                    'customer_rank': 1,
                })
            else:
                p.write({'customer_tier_id': tier.id})

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
        for pname, tier_code in existing_map.items():
            tier = tiers_by_code.get(tier_code)
            ep = partner_obj.search([('name', 'ilike', pname)], limit=1)
            if ep and tier:
                ep.write({'customer_tier_id': tier.id})

        # 1b. Seed product categories + a category-specific ceiling on the Gold tier so the
        #     "Gold gets 15% on Hardware but only 8% on Services" rule is demoable in one click.
        categ_obj = self.env['product.category'].sudo()
        hardware_categ = categ_obj.search([('name', '=', 'DealFlow Hardware')], limit=1) or \
            categ_obj.create({'name': 'DealFlow Hardware'})
        services_categ = categ_obj.search([('name', '=', 'DealFlow Services')], limit=1) or \
            categ_obj.create({'name': 'DealFlow Services'})

        gold_tier = tiers_by_code.get('gold')
        if gold_tier and not gold_tier.category_ceiling_ids.filtered(
                lambda c: c.product_category_id == services_categ):
            self.env['vantage.discount.tier.category'].sudo().create({
                'tier_id': gold_tier.id,
                'product_category_id': services_categ.id,
                'discount_ceiling': 8.0,
            })

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

        # Third regional depot: proves the allocation engine is N-way, not primary+secondary.
        west_wh = warehouse_obj.search([('code', '=', 'WEST')], limit=1)
        west_vals = {
            'name': 'West Hub',
            'code': 'WEST',
            'shipping_cost_weight': 2.0,
            'base_shipping_cost': 45.0,
        }
        if west_wh:
            west_wh.write(west_vals)
        else:
            west_wh = warehouse_obj.create(west_vals)

        for wh in (main_wh, east_wh, west_wh):
            wh.write({'vantage_allow_split_source': True})

        # 3. Seed Demo Products
        # Hardware: DealFlow Enterprise Server (Storable)
        server_vals = {
            'name': 'DealFlow Enterprise Server',
            'type': 'product',
            'list_price': 2500.0,
            'standard_price': 1500.0,
            'default_code': 'DF-SRV-01',
            'categ_id': hardware_categ.id,
        }
        server_prod = product_obj.search([('name', '=', 'DealFlow Enterprise Server')], limit=1)
        if not server_prod:
            server_prod = product_obj.create(server_vals)
        else:
            server_prod.write(server_vals)

        # Service: Enterprise Setup & Deployment
        setup_vals = {
            'name': 'Enterprise Setup & Deployment',
            'type': 'service',
            'list_price': 1200.0,
            'standard_price': 800.0,
            'default_code': 'DF-SRV-SET',
            'categ_id': services_categ.id,
        }
        setup_prod = product_obj.search([('name', '=', 'Enterprise Setup & Deployment')], limit=1)
        if not setup_prod:
            setup_prod = product_obj.create(setup_vals)
        else:
            setup_prod.write(setup_vals)

        # Subscription: DealFlow360 SaaS License — quarterly cadence over a 12-month contract
        sub_vals = {
            'name': 'DealFlow360 SaaS Annual License',
            'type': 'service',
            'list_price': 600.0,
            'standard_price': 50.0,
            'default_code': 'DF-SAAS-ANN',
            'categ_id': services_categ.id,
            'vantage_is_subscription': True,
            'vantage_billing_cadence': 'quarterly',
            'vantage_contract_months': 12,
            'vantage_price_basis': 'contract',
        }
        sub_prod = product_obj.search([('name', '=', 'DealFlow360 SaaS Annual License')], limit=1)
        if not sub_prod:
            sub_prod = product_obj.create(sub_vals)
        else:
            sub_prod.write(sub_vals)

        # Upsell Option: 24/7 Mission-Critical SLA Warranty
        sla_vals = {
            'name': '24/7 Mission-Critical SLA Warranty',
            'type': 'service',
            'list_price': 450.0,
            'standard_price': 100.0,
            'default_code': 'DF-SLA-247',
            'categ_id': services_categ.id,
        }
        sla_prod = product_obj.search([('name', '=', '24/7 Mission-Critical SLA Warranty')], limit=1)
        if not sla_prod:
            sla_prod = product_obj.create(sla_vals)
        else:
            sla_prod.write(sla_vals)

        # 4. Seed Stock Quants across THREE depots so the bundle's 10 servers genuinely
        #    need a 3-way split: Main 5 + West 3 + East 2. Ranking is by landed leg cost
        #    (Main $25, West $45x2.0=$90, East $60x2.5=$150), so the engine fills the
        #    cheap depots first and only touches East for the last 2 units.
        quant_mode = self.env['stock.quant'].with_context(inventory_mode=True).sudo()
        stock_plan = [(main_wh, 5.0), (west_wh, 3.0), (east_wh, 6.0)]
        for warehouse, target_free in stock_plan:
            location = warehouse.lot_stock_id
            if not location or not server_prod:
                continue
            quant = quant_mode.search([
                ('product_id', '=', server_prod.id), ('location_id', '=', location.id),
            ], limit=1)
            # Earlier demo orders may hold reservations against this depot. Inventory
            # adjustments set the on-hand figure, so top up over whatever is reserved to
            # land on the intended *free* quantity — otherwise re-seeding leaves a depot
            # looking empty to the allocation engine.
            reserved = quant.reserved_quantity if quant else 0.0
            target_on_hand = target_free + reserved
            if quant and abs(quant.quantity - target_on_hand) < 0.001:
                continue
            if not quant:
                quant = quant_mode.create({
                    'product_id': server_prod.id,
                    'location_id': location.id,
                    'inventory_quantity': target_on_hand,
                })
            else:
                quant.inventory_quantity = target_on_hand
            quant.action_apply_inventory()

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
                    'Pre-seeded Bronze/Silver/Gold tiers (Gold capped at 8%% on Services), three '
                    'regional depots — Main 5u/$25, West Hub 3u/$45x2.0, East Depot 6u/$60x2.5 — '
                    'a quarterly SaaS subscription, demo products and Smart Upsell Rules.'
                ),
                'sticky': False,
                'type': 'success',
                'next': {'type': 'ir.actions.client', 'tag': 'reload'}
            }
        }

