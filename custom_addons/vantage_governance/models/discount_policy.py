from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class VantageDiscountTier(models.Model):
    """Customer tier policy: the discount ceilings that used to be a Python dict.

    Administrators can now create any number of tiers (Platinum, Distributor,
    Government, ...) and give each one its own baseline ceiling, per-product-category
    overrides, negotiation budget and manager approval ceiling.
    """
    _name = 'vantage.discount.tier'
    _description = 'VantageOps Customer Discount Tier Policy'
    _order = 'sequence, discount_ceiling, id'

    name = fields.Char(string='Tier Name', required=True, translate=True)
    code = fields.Char(
        string='Technical Code', required=True,
        help="Stable key used by imports and migrations (e.g. bronze, silver, gold)."
    )
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)
    is_default = fields.Boolean(
        string='Default Tier',
        help="Tier assigned to new customers and used when a customer has no tier set."
    )

    discount_ceiling = fields.Float(
        string='Baseline Discount Ceiling (%)', default=10.0, required=True,
        help="Maximum discount a rep may grant without triggering the approval workflow."
    )
    category_ceiling_ids = fields.One2many(
        'vantage.discount.tier.category', 'tier_id',
        string='Product Category Overrides',
        help="Narrower ceilings for specific product categories (e.g. thin-margin Services)."
    )

    manager_risk_ceiling = fields.Float(
        string='Manager Approval Ceiling Override', default=0.0,
        help="Highest blended risk score a Sales Manager may sign off for this tier. "
             "Leave at 0 to inherit the global value from Sales Settings."
    )
    max_negotiation_rounds = fields.Integer(
        string='Negotiation Rounds Override', default=0,
        help="Counter-offer rounds allowed before the circuit breaker locks the deal. "
             "Leave at 0 to inherit the sales team or global value."
    )

    badge_color = fields.Selection([
        ('muted', 'Grey'),
        ('info', 'Blue'),
        ('primary', 'Indigo'),
        ('success', 'Green'),
        ('warning', 'Amber'),
        ('danger', 'Red'),
    ], string='Badge Colour', default='info')
    note = fields.Text(string='Policy Notes')

    partner_ids = fields.One2many('res.partner', 'customer_tier_id', string='Classified Customers')
    partner_count = fields.Integer(string='Customers', compute='_compute_partner_count')

    _sql_constraints = [
        ('vantage_tier_code_uniq', 'unique(code)', 'The tier technical code must be unique.'),
    ]

    @api.depends('partner_ids')
    def _compute_partner_count(self):
        grouped = self.env['res.partner']._read_group(
            [('customer_tier_id', 'in', self.ids)], ['customer_tier_id'], ['__count'],
        )
        counts = {tier.id: count for tier, count in grouped}
        for tier in self:
            tier.partner_count = counts.get(tier.id, 0)

    @api.depends('name', 'discount_ceiling')
    def _compute_display_name(self):
        for tier in self:
            tier.display_name = _('%(name)s (%(ceiling)g%% ceiling)',
                                  name=tier.name or '', ceiling=tier.discount_ceiling)

    @api.constrains('discount_ceiling')
    def _check_discount_ceiling(self):
        for tier in self:
            if not 0.0 <= tier.discount_ceiling <= 100.0:
                raise ValidationError(_("The baseline discount ceiling must be between 0%% and 100%%."))

    @api.constrains('manager_risk_ceiling', 'max_negotiation_rounds')
    def _check_non_negative(self):
        for tier in self:
            if tier.manager_risk_ceiling < 0.0 or tier.max_negotiation_rounds < 0:
                raise ValidationError(_("Approval ceilings and negotiation rounds cannot be negative."))

    @api.constrains('is_default', 'active')
    def _check_single_default(self):
        for tier in self.filtered(lambda t: t.is_default and t.active):
            duplicate = self.search([
                ('is_default', '=', True), ('active', '=', True), ('id', '!=', tier.id),
            ], limit=1)
            if duplicate:
                raise ValidationError(_(
                    "Only one tier can be the default. '%s' is already flagged as default.",
                    duplicate.name,
                ))

    @api.model
    def _get_default_tier(self):
        """Tier applied to customers that have not been classified yet."""
        return self.search([('is_default', '=', True)], limit=1)

    def get_ceiling_for_product(self, product=None):
        """Resolve the discount ceiling for a product, most specific category wins.

        The override lookup walks up the product category tree, so an override on
        "Services" also covers "Services / Professional Services" unless that child
        has an override of its own.
        """
        self.ensure_one()
        category = product.categ_id if product else False
        if category and self.category_ceiling_ids:
            overrides = {c.product_category_id.id: c.discount_ceiling for c in self.category_ceiling_ids}
            node = category
            while node:
                if node.id in overrides:
                    return overrides[node.id]
                node = node.parent_id
        return self.discount_ceiling

    def action_view_partners(self):
        self.ensure_one()
        return {
            'name': _('%s Customers') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'res.partner',
            'view_mode': 'tree,form',
            'domain': [('customer_tier_id', '=', self.id)],
            'context': {'default_customer_tier_id': self.id},
        }


class VantageDiscountTierCategory(models.Model):
    _name = 'vantage.discount.tier.category'
    _description = 'Category-Specific Discount Ceiling'
    _order = 'tier_id, product_category_id'

    tier_id = fields.Many2one(
        'vantage.discount.tier', string='Tier', required=True, ondelete='cascade', index=True
    )
    product_category_id = fields.Many2one(
        'product.category', string='Product Category', required=True, ondelete='cascade'
    )
    discount_ceiling = fields.Float(string='Discount Ceiling (%)', required=True, default=10.0)

    _sql_constraints = [
        ('vantage_tier_category_uniq', 'unique(tier_id, product_category_id)',
         'This product category already has a ceiling defined for that tier.'),
    ]

    @api.constrains('discount_ceiling')
    def _check_discount_ceiling(self):
        for override in self:
            if not 0.0 <= override.discount_ceiling <= 100.0:
                raise ValidationError(_("A category discount ceiling must be between 0%% and 100%%."))
