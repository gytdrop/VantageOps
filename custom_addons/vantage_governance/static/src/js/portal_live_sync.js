/** @odoo-module **/
import { registry } from "@web/core/registry";

export const portalDealSyncService = {
    dependencies: ["bus_service"],
    start(env, { bus_service }) {
        function initPortalSync() {
            const orderElem = document.querySelector('[data-order-id]');
            if (!orderElem) return;

            const orderId = orderElem.getAttribute('data-order-id');
            const channel = `vantage_order_${orderId}`;

            if (bus_service) {
                bus_service.addChannel(channel);
                bus_service.subscribe("vantage_sync", (payload) => {
                    if (payload && (!payload.order_id || payload.order_id == orderId)) {
                        // Instantly reload portal DOM to reflect updated terms & approvals
                        window.location.reload();
                    }
                });
            }
        }

        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", initPortalSync);
        } else {
            initPortalSync();
        }
    },
};

registry.category("services").add("portalDealSync", portalDealSyncService);
