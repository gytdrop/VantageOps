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

    @http.route(['/my/orders/<int:order_id>/counter_offer', '/vantage/portal/counter_offer'], type='http', auth="public", methods=['POST'], website=True, csrf=False)
    def portal_order_counter_offer(self, order_id=None, line_id=None, counter_discount=0.0, notes="", counter_note=None, access_token=None, **post):
        target_id = order_id or post.get('order_id')
        if not target_id:
            return request.redirect('/my')
        order_sudo = request.env['sale.order'].sudo().browse(int(target_id))
        if not order_sudo.exists():
            return request.redirect('/my')

        try:
            discount_val = float(counter_discount)
            note_val = counter_note or notes or post.get('notes') or ""
            order_sudo.action_customer_counter_offer(
                line_id=line_id,
                counter_discount=discount_val,
                notes=note_val
            )
            request.session['portal_success'] = f"Counter-offer of {discount_val}% submitted successfully! VantageOps governance engine re-evaluated deal risk."
        except Exception as e:
            request.session['portal_error'] = str(e)

        portal_url = order_sudo.get_portal_url()
        if '#' not in portal_url:
            portal_url += '#deal_negotiation_portal'
        return request.redirect(portal_url)

    @http.route('/vantage/portal/razorpay_callback', type='json', auth="public", methods=['POST'], website=True, csrf=False)
    def portal_razorpay_callback(self, order_id=None, payment_id=None, **kw):
        data = request.jsonrequest.get('params', {}) if hasattr(request, 'jsonrequest') and request.jsonrequest else kw
        target_id = order_id or data.get('order_id') or kw.get('order_id')
        txn_id = payment_id or data.get('payment_id') or kw.get('payment_id') or 'pay_mock_12345'
        if not target_id:
            return {'status': 'error', 'message': 'Missing order_id'}
        order_sudo = request.env['sale.order'].sudo().browse(int(target_id))
        if order_sudo.exists():
            # Force approval & confirm quotation upon successful payment
            order_sudo.write({'risk_approval_state': 'approved'})
            if order_sudo.state in ('draft', 'sent'):
                order_sudo.action_confirm()
            order_sudo.message_post(
                body=f"💳 <strong>Razorpay Online Payment Captured &amp; Order Confirmed</strong><br/>"
                     f"Transaction ID: <code>{txn_id}</code><br/>"
                     f"Amount Received: ₹{order_sudo.amount_total:,.2f}"
            )
            request.session['portal_success'] = f"Payment of ₹{order_sudo.amount_total:,.2f} via Razorpay (ID: {txn_id}) captured! Order {order_sudo.name} confirmed."
            return {'status': 'success'}
        return {'status': 'error', 'message': 'Order not found'}


