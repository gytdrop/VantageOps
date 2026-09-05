from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # --- Multi-depot allocation ---
    vantage_max_split_legs = fields.Integer(
        string='Maximum Depots per Order', default=0,
        config_parameter='vantage.max_split_legs',
        help="Cap on how many warehouses a single order may ship from. 0 means unlimited — "
             "the engine keeps adding depots until the demand is covered."
    )

    # --- Subscription billing ---
    vantage_default_contract_months = fields.Integer(
        string='Default Contract Length (Months)', default=12,
        config_parameter='vantage.default_contract_months',
        help="Applied to subscription products that do not define their own contract length."
    )
    vantage_default_cadence = fields.Selection([
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('semi_annual', 'Semi-Annual'),
        ('annual', 'Annual'),
    ], string='Default Billing Cadence', default='monthly',
        config_parameter='vantage.default_cadence',
        help="Cadence used when a subscription product has none configured."
    )
    vantage_subscription_anchor = fields.Selection([
        ('service_start', 'Anniversary (cycles run from the service start date)'),
        ('calendar', 'Calendar-Aligned (cycles snap to month/quarter/year boundaries)'),
    ], string='Default Cycle Anchor', default='service_start',
        config_parameter='vantage.subscription_anchor',
        help="Calendar alignment is what produces prorated first and last cycles."
    )
