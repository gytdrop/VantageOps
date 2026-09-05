from odoo import models, fields, api, _


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # --- Risk scoring ---
    vantage_default_discount_ceiling = fields.Float(
        string='Fallback Discount Ceiling (%)', default=10.0,
        config_parameter='vantage.default_discount_ceiling',
        help="Ceiling applied to customers that have not been assigned a tier yet."
    )
    vantage_breach_weight = fields.Float(
        string='Worst-Breach Weight', default=0.6,
        config_parameter='vantage.breach_weight',
        help="Weight of the single worst discount breach in the blended risk score."
    )
    vantage_margin_loss_weight = fields.Float(
        string='Margin-Loss Weight', default=0.4,
        config_parameter='vantage.margin_loss_weight',
        help="Weight of the order-wide excess margin loss in the blended risk score."
    )

    # --- Approval routing ---
    vantage_risk_trigger_threshold = fields.Float(
        string='Approval Trigger Threshold', default=0.0,
        config_parameter='vantage.risk_trigger_threshold',
        help="Deals scoring above this value are routed into the approval workflow and "
             "blocked from confirmation."
    )
    vantage_manager_risk_ceiling = fields.Float(
        string='Manager Approval Ceiling', default=10.0,
        config_parameter='vantage.manager_risk_ceiling',
        help="Highest blended risk score a Sales Manager may approve alone. Anything above "
             "escalates to the Finance Director. Customer tiers may override this."
    )

    # --- Circuit breaker ---
    vantage_default_max_negotiation_rounds = fields.Integer(
        string='Default Negotiation Rounds', default=3,
        config_parameter='vantage.default_max_negotiation_rounds',
        help="Counter-offer rounds allowed before the negotiation circuit breaker trips, "
             "unless overridden on the sales team or the customer tier."
    )

    # --- Deal health heuristics ---
    vantage_stalled_days = fields.Integer(
        string='Stalled After (Days)', default=3,
        config_parameter='vantage.stalled_days',
        help="Days of inactivity after which an open quotation is flagged as stalled."
    )
    vantage_margin_bleed_threshold = fields.Float(
        string='Margin Bleed Score', default=15.0,
        config_parameter='vantage.margin_bleed_threshold',
        help="Blended risk score above which a deal is flagged as critical margin bleed."
    )
    vantage_discount_anomaly_threshold = fields.Float(
        string='Discount Anomaly (%)', default=20.0,
        config_parameter='vantage.discount_anomaly_threshold',
        help="Average order discount above which the deal is flagged as an anomaly."
    )

    def action_vantage_open_tiers(self):
        return self.env['ir.actions.act_window']._for_xml_id('vantage_governance.action_vantage_discount_tier')

    def action_vantage_recompute_risk(self):
        """Re-run the risk engine on open deals after the thresholds have changed.

        Config parameters cannot appear in an @api.depends chain, so stored scores of
        existing quotations would otherwise keep the values from the previous policy.
        """
        orders = self.env['sale.order'].search([('state', 'in', ('draft', 'sent'))])
        if orders:
            orders.invalidate_recordset(['blended_risk_score', 'deal_health', 'days_inactive',
                                         'discount_anomaly', 'max_negotiation_rounds'])
            orders.modified(['order_line'])
            orders._compute_vantage_risk()
            orders._compute_deal_health()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Governance Policy Applied'),
                'message': _('%s open quotation(s) re-scored against the current thresholds.') % len(orders),
                'type': 'success',
                'sticky': False,
            },
        }
