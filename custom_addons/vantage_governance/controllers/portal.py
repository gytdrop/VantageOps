# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from odoo.addons.sale.controllers.portal import CustomerPortal

class VantageCustomerPortal(CustomerPortal):

    def _prepare_quotations_domain(self, partner):
        """Allow portal customers to view and negotiate draft and sent quotations."""
        return [
            '|',
            ('message_partner_ids', 'child_of', [partner.commercial_partner_id.id]),
            ('partner_id', 'child_of', [partner.commercial_partner_id.id]),
            ('state', 'in', ['draft', 'sent'])
        ]

    @http.route(['/my/orders/<int:order_id>/counter_offer'], type='http', auth="public", methods=['POST'], website=True, csrf=False)
    def portal_order_counter_offer(self, order_id, line_id=None, counter_discount=0.0, notes="", access_token=None, **post):
        order_sudo = request.env['sale.order'].sudo().browse(order_id)
        if not order_sudo.exists():
            return request.redirect('/my')

        try:
            discount_val = float(counter_discount)
            order_sudo.action_customer_counter_offer(
                line_id=line_id,
                counter_discount=discount_val,
                notes=notes
            )
            request.session['portal_success'] = f"Counter-offer of {discount_val}% submitted successfully! VantageOps governance engine re-evaluated deal risk."
        except Exception as e:
            request.session['portal_error'] = str(e)

        portal_url = order_sudo.get_portal_url()
        if '#' not in portal_url:
            portal_url += '#deal_negotiation_portal'
        return request.redirect(portal_url)
