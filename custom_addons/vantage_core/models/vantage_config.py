from odoo import api, models

# Every VantageOps tunable lives under this ir.config_parameter namespace so that
# `Settings > Sales > VantageOps ...` and Technical > System Parameters stay in sync.
VANTAGE_PREFIX = 'vantage.'

# Billing cadences shared by products, order lines and the billing schedule engine.
CADENCE_SELECTION = [
    ('monthly', 'Monthly'),
    ('quarterly', 'Quarterly'),
    ('semi_annual', 'Semi-Annual'),
    ('annual', 'Annual'),
]
CADENCE_MONTHS = {
    'monthly': 1,
    'quarterly': 3,
    'semi_annual': 6,
    'annual': 12,
}


class VantageConfig(models.AbstractModel):
    """Typed accessor for the VantageOps tunables stored as system parameters.

    Business rules used to be literals scattered through the compute methods.
    They now resolve through this helper, which always falls back to the shipped
    default when a parameter has never been saved from the settings screen.
    """
    _name = 'vantage.config'
    _description = 'VantageOps Configuration Accessor'

    @api.model
    def _raw(self, key):
        value = self.env['ir.config_parameter'].sudo().get_param(VANTAGE_PREFIX + key)
        return value if value not in (None, False, '') else None

    @api.model
    def get_float(self, key, default=0.0):
        value = self._raw(key)
        try:
            return float(value) if value is not None else float(default)
        except (TypeError, ValueError):
            return float(default)

    @api.model
    def get_int(self, key, default=0):
        value = self._raw(key)
        try:
            return int(float(value)) if value is not None else int(default)
        except (TypeError, ValueError):
            return int(default)

    @api.model
    def get_bool(self, key, default=False):
        value = self._raw(key)
        if value is None:
            return bool(default)
        return str(value).strip().lower() in ('1', 'true', 't', 'yes')

    @api.model
    def get_str(self, key, default=''):
        value = self._raw(key)
        return value if value is not None else default

    @api.model
    def get_selection(self, key, allowed, default):
        """Return a stored selection value, guarding against stale/invalid keys."""
        value = self._raw(key)
        return value if value in allowed else default
