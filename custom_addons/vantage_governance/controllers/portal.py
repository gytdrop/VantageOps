from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal

class VantageCustomerPortal(CustomerPortal):

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
        except Exception as e:
            request.session['portal_error'] = str(e)

        return request.redirect(order_sudo.get_portal_url(access_token=access_token))
