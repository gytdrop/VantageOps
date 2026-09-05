"""Adopt orphaned discount-tier rows so the shipped data file can never collide with them.

`vantage.discount.tier` has a UNIQUE constraint on `code`. If an upgrade is interrupted
after the tier rows commit but before their `ir_model_data` XML-IDs do, the next upgrade
finds no XML-ID, tries to INSERT Bronze/Silver/Gold again and dies on that constraint —
taking the whole registry load with it (exit 255).

Re-pointing the expected XML-IDs at the existing rows makes the data file update them in
place instead of inserting, so the upgrade is idempotent from any partially-applied state.
"""
import logging

from odoo.tools import sql

_logger = logging.getLogger(__name__)

# code -> the XML-ID declared in data/discount_tier_data.xml
XMLID_BY_CODE = {
    'bronze': 'vantage_tier_bronze',
    'silver': 'vantage_tier_silver',
    'gold': 'vantage_tier_gold',
}


def migrate(cr, version):
    if not version:
        return
    if not sql.table_exists(cr, 'vantage_discount_tier'):
        return

    cr.execute("""
        SELECT t.id, t.code
          FROM vantage_discount_tier t
     LEFT JOIN ir_model_data d
            ON d.model = 'vantage.discount.tier' AND d.res_id = t.id
         WHERE d.id IS NULL
    """)
    orphans = cr.fetchall()
    if not orphans:
        return

    adopted = 0
    for tier_id, code in orphans:
        xmlid = XMLID_BY_CODE.get(code)
        if not xmlid:
            # A tier an administrator created by hand; it has no XML-ID by design.
            continue
        cr.execute("""
            INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
                 VALUES ('vantage_governance', %s, 'vantage.discount.tier', %s, TRUE)
            ON CONFLICT (module, name) DO UPDATE SET res_id = EXCLUDED.res_id
        """, (xmlid, tier_id))
        adopted += 1

    _logger.info("VantageOps: adopted %s orphaned discount tier(s) into ir_model_data.", adopted)
