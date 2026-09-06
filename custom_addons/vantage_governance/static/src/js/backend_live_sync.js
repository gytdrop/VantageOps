/** @odoo-module **/
import { registry } from "@web/core/registry";

function ensureKanbanPipelineStyles() {
    if (typeof document === "undefined") return;
    let style = document.getElementById("vantage-kanban-pipeline-style");
    if (!style) {
        style = document.createElement("style");
        style.id = "vantage-kanban-pipeline-style";
        document.head.appendChild(style);
    }
    style.textContent = `
        /* VantageOps Governance Pipeline - 100% Screen Stretch & Independent Column Scroll */
        .o_kanban_view.o_vantage_full_kanban,
        .o_kanban_view:has(.o_vantage_kanban_card),
        .o_view_controller:has(.o_vantage_kanban_card) {
            display: flex !important;
            flex-direction: column !important;
            width: 100% !important;
            height: 100% !important;
            max-height: 100% !important;
            overflow: hidden !important;
        }
        .o_kanban_view.o_vantage_full_kanban .o_content,
        .o_kanban_view:has(.o_vantage_kanban_card) .o_content,
        .o_content:has(.o_vantage_kanban_card) {
            height: 100% !important;
            max-height: 100% !important;
            min-height: 0 !important;
            overflow-y: hidden !important;
            overflow-x: auto !important;
            display: flex !important;
            flex-direction: column !important;
            width: 100% !important;
        }
        .o_kanban_renderer.o_kanban_grouped.o_vantage_full_kanban,
        .o_kanban_renderer.o_kanban_grouped.o_vantage_kanban_pipeline,
        .o_kanban_view.o_vantage_full_kanban .o_kanban_renderer,
        .o_kanban_renderer.o_kanban_grouped:has(.o_vantage_kanban_card) {
            height: 100% !important;
            max-height: 100% !important;
            min-height: 0 !important;
            flex: 1 1 auto !important;
            overflow-y: hidden !important;
            overflow-x: auto !important;
            display: flex !important;
            flex-direction: row !important;
            align-items: stretch !important;
            justify-content: space-between !important;
            width: 100% !important;
            padding: 14px 16px !important;
            gap: 14px !important;
            box-sizing: border-box !important;
            background-color: #f1f5f9 !important;
        }
        .o_kanban_renderer.o_kanban_grouped.o_vantage_full_kanban .o_kanban_group,
        .o_kanban_renderer.o_kanban_grouped.o_vantage_kanban_pipeline .o_kanban_group,
        .o_kanban_view.o_vantage_full_kanban .o_kanban_group,
        .o_kanban_renderer.o_kanban_grouped:has(.o_vantage_kanban_card) .o_kanban_group {
            height: 100% !important;
            max-height: 100% !important;
            min-height: 0 !important;
            display: flex !important;
            flex-direction: column !important;
            overflow-y: auto !important;
            overflow-x: hidden !important;
            background-color: #f8fafc !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 10px !important;
            padding: 0 10px 12px 10px !important;
            margin-right: 0 !important;
            flex: 1 1 0 !important;
            min-width: 230px !important;
            max-width: none !important;
            box-sizing: border-box !important;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05) !important;
            scrollbar-width: thin !important;
            scrollbar-color: #94a3b8 transparent !important;
        }
        .o_kanban_renderer.o_kanban_grouped .o_kanban_group::-webkit-scrollbar {
            width: 6px !important;
        }
        .o_kanban_renderer.o_kanban_grouped .o_kanban_group::-webkit-scrollbar-thumb {
            background-color: #cbd5e1 !important;
            border-radius: 3px !important;
        }
        .o_kanban_renderer.o_kanban_grouped.o_vantage_full_kanban .o_kanban_group:not(.o_column_folded) .o_kanban_header,
        .o_kanban_renderer.o_kanban_grouped.o_vantage_kanban_pipeline .o_kanban_group:not(.o_column_folded) .o_kanban_header,
        .o_kanban_view.o_vantage_full_kanban .o_kanban_group:not(.o_column_folded) .o_kanban_header,
        .o_kanban_renderer.o_kanban_grouped:has(.o_vantage_kanban_card) .o_kanban_group:not(.o_column_folded) .o_kanban_header {
            position: sticky !important;
            top: 0 !important;
            z-index: 10 !important;
            background-color: #f8fafc !important;
            padding-top: 12px !important;
            padding-bottom: 8px !important;
            border-bottom: 2px solid #e2e8f0 !important;
            margin-bottom: 12px !important;
            flex-shrink: 0 !important;
        }
        .o_kanban_renderer.o_kanban_grouped.o_vantage_full_kanban .o_kanban_group.o_column_folded,
        .o_kanban_renderer.o_kanban_grouped.o_vantage_kanban_pipeline .o_kanban_group.o_column_folded,
        .o_kanban_view.o_vantage_full_kanban .o_kanban_group.o_column_folded,
        .o_kanban_renderer.o_kanban_grouped:has(.o_vantage_kanban_card) .o_kanban_group.o_column_folded {
            flex: 0 0 42px !important;
            min-width: 42px !important;
            max-width: 42px !important;
            overflow: hidden !important;
            padding: 0 4px !important;
            background-color: #f1f5f9 !important;
        }
        .o_kanban_renderer.o_kanban_grouped .o_kanban_record {
            flex-shrink: 0 !important;
            width: 100% !important;
            margin-bottom: 8px !important;
        }
        .o_vantage_kanban_card {
            transition: transform 0.15s ease, box-shadow 0.15s ease;
            border: 1px solid #e2e8f0 !important;
        }
        .o_vantage_kanban_card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.1) !important;
            border-color: #cbd5e1 !important;
        }
        .o_kanban_renderer.o_kanban_grouped .o_kanban_load_more {
            flex-shrink: 0 !important;
            margin-top: 8px !important;
            padding-bottom: 6px !important;
        }
    `;
}

// Invoke style injection immediately on load
ensureKanbanPipelineStyles();

export const vantageBackendSyncService = {
    dependencies: ["bus_service", "action"],
    start(env, { bus_service, action }) {
        ensureKanbanPipelineStyles();
        if (!bus_service) return;
        bus_service.subscribe("vantage_sync", (payload) => {
            if (!payload || !payload.order_id) return;
            const controller = action.currentController;
            if (controller && controller.props && controller.props.resModel === "sale.order") {
                if (controller.props.resId === payload.order_id) {
                    // Silently reload the active quotation form view data
                    if (controller.model && controller.model.root && typeof controller.model.root.load === "function") {
                        controller.model.root.load();
                    }
                } else if (!controller.props.resId && controller.model && controller.model.root && typeof controller.model.root.load === "function") {
                    // Reload quotation list/kanban view
                    controller.model.root.load();
                }
            }
        });
    },
};

registry.category("services").add("vantageBackendSync", vantageBackendSyncService);
