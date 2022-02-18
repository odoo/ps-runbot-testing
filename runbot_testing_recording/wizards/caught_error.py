import autopep8
from odoo import models, api, fields, _
from ..controllers.main import format_python

class RunbotRecordingError(models.TransientModel):
    _name = 'runbot.record.error'
    _description = 'Runbot error record'


    error_type = fields.Char(string='Error type', readonly=True)
    description = fields.Text(string='Description', readonly=True)

    def record_error(self):
        test_id = int(self.env['ir.config_parameter'].sudo().get_param('runbot.record.current', '0'))
        test_id = self.env['runbot.record'].browse(test_id)
        if not self.env.context.get('error_caught_params') or not test_id:
            return
        params = self.env.context['error_caught_params']
        error_call = format_python(params['model'], params['method'], params.get('args', []), params.get('kwargs', {}))

        savepoint = 'self.cr.execute(\'SAVEPOINT test_error\')'
        withassert = 'with self.assertRaises(%s):' % (self.error_type)
        error_call = '    ' + error_call.replace('\n', '\n    ')
        rollback = 'self.cr.execute(\'ROLLBACK TO SAVEPOINT test_error\')'
        call = '\n'.join([savepoint, withassert, error_call, rollback])
        content = '\n'.join([test_id.content or '', call])
        test_id.content = content
