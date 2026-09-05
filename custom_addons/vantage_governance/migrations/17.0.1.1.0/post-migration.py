"""Carry legacy `res_partner.customer_tier` selection values onto the new tier records.

The tier ceilings used to be a Python dict keyed by a selection field storing
'bronze' / 'silver' / 'gold'. They are now rows of `vantage.discount.tier`, linked
from `res_partner.customer_tier_id`. This runs after the module's data files have
created the shipped tiers and before Odoo drops the obsolete column at the end of
the upgrade, so the classification customers already have is preserved.
"""
import logging

from odoo import api, SUPERUSER_ID
from odoo.tools import sql

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    if not sql.column_exists(cr, 'res_partner', 'customer_tier'):
        _logger.info("VantageOps: no legacy customer_tier column, nothing to migrate.")
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    tiers = env['vantage.discount.tier'].search([])
    by_code = {tier.code: tier.id for tier in tiers if tier.code}
    if not by_code:
        _logger.warning("VantageOps: no discount tiers found, skipping customer tier migration.")
        return

    # Deliberately not filtered on `customer_tier_id IS NULL`: Odoo's _init_column has
    # already stamped every existing row with the field default (the tier flagged
    # is_default), so that guard would match nothing and silently drop the real
    # classification. This hop runs once, version-gated, so the legacy value wins.
    cr.execute("""
        SELECT customer_tier, array_agg(id)
          FROM res_partner
         WHERE customer_tier IS NOT NULL
      GROUP BY customer_tier
    """)
    migrated = 0
    for legacy_code, partner_ids in cr.fetchall():
        tier_id = by_code.get(legacy_code)
        if not tier_id:
            _logger.warning("VantageOps: legacy tier %r has no matching vantage.discount.tier, "
                            "%s partner(s) left unclassified.", legacy_code, len(partner_ids))
            continue
        cr.execute(
            "UPDATE res_partner SET customer_tier_id = %s WHERE id = ANY(%s)",
            (tier_id, list(partner_ids)),
        )
        migrated += len(partner_ids)

    _logger.info("VantageOps: migrated %s partner(s) onto configurable discount tiers.", migrated)
