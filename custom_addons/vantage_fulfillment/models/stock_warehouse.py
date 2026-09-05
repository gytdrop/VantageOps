from odoo import models, fields, api


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
    vantage_effective_ship_cost = fields.Float(
        string='Landed Leg Cost ($)',
        compute='_compute_vantage_effective_ship_cost',
        store=True,
        help="Base dispatch cost × distance weight. The allocation engine ranks depots by this figure."
    )
    vantage_allow_split_source = fields.Boolean(
        string='Available for Auto-Split',
        default=True,
        help="Untick to keep this warehouse out of the multi-depot allocation engine "
             "(e.g. a quarantine or returns location)."
    )
    vantage_split_priority = fields.Integer(
        string='Allocation Priority',
        default=10,
        help="Tie-breaker when several depots have the same landed cost. Lower is preferred."
    )

    @api.depends('base_shipping_cost', 'shipping_cost_weight')
    def _compute_vantage_effective_ship_cost(self):
        for warehouse in self:
            base = warehouse.base_shipping_cost or 25.0
            weight = warehouse.shipping_cost_weight or 1.0
            warehouse.vantage_effective_ship_cost = round(base * weight, 2)
