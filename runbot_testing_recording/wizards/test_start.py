from odoo import models, api, fields, _
import autopep8


class RunbotRecordingTEST(models.TransientModel):
    _name = 'runbot.record.test'

    description = fields.Text(string='Description', required=True)

    def save(self):
        recording_id = int(self.env['ir.config_parameter'].get_param('runbot.record.current', '0'))
        recording = self.env['runbot.record'].search([('id','=', recording_id)])
        description = '\'\'\'TODO: DO A TEST HERE: \n %s \n\'\'\'' % (self.description)
        if recording:
            content = '\n'.join([recording.content or '', description])
            content = autopep8.fix_code(content, options={'aggressive': 1})
            recording.content = content

        self.env['runbot.record.line'].create({
            'record_id': recording.id,
            'description': self.description,
            'sequence': recording.line_ids and max(recording.line_ids.mapped('sequence'))+1 or 1
            })
