from odoo import models, fields

class HackathonItemFeatureB(models.Model):
    _inherit = 'hackathon.item'  # Extends hackathon.item without touching core files

    ai_summary = fields.Text(string='AI Summary')

    def action_run_analysis(self):
        for record in self:
            record.ai_summary = f"Analysis generated for item: {record.name}"
