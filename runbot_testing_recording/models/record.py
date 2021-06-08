# -*- coding: utf-8 -*-
import autopep8
import ast

from odoo import http, models, fields, api
from odoo.exceptions import UserError

class RunbotRecording(models.Model):
    _name = 'runbot.record'
    _description = 'Runbot test flow'
    _order = 'id desc'

    start_date = fields.Datetime(string="Start Date", default=lambda self: fields.datetime.now())
    name = fields.Char(string="Title", required=True)
    module_id = fields.Many2one('ir.module.module', string="Module to apply tests to", required=True, ondelete='cascade')
    description = fields.Text(string='Description')
    record_type = fields.Selection([
        ('demo', 'Demo Data'),
        ('test', 'Test flow'),
    ], string="Type", default='test', required=True)
    content = fields.Text(string='Content')
    line_ids = fields.One2many(
        'runbot.record.line',
        'record_id',
        string='Tests',
    )
    reference_ids = fields.One2many(
        'runbot.record.reference',
        'record_id',
        string='Reference',
    )

    @api.model
    def open_registration(self):
        if ast.literal_eval(self.env['ir.config_parameter'].get_param('runbot.record.demo', 'False')):
            raise UserError('Already set to record demo datas')
        if ast.literal_eval(self.env['ir.config_parameter'].get_param('runbot.record.test', 'False')):
            raise UserError('Already set to record a test flow')
        view_id =  self.env.ref('runbot_testing_recording.runbot_record_form_view_wizard').id
        return {
            'name': 'Record test',
            'type': 'ir.actions.act_window',
            'res_model': 'runbot.record',
            'views': [[view_id, 'form']],
            'view_mode': 'form',
            'context': self.env.context,
            'target': 'new',
        }
  
    def start_recording(self):
        self.ensure_one()
        content = '\'\'\'\n%s\n\'\'\'' % (self.description) if self.record_type == 'test' else '<!--\n%s\n-->' % (self.description)
        self.content = content
        self.env['ir.config_parameter'].set_param('runbot.record.%s' % (self.record_type), 'True')
        self.env['ir.config_parameter'].set_param('runbot.record.current', self.id)

    @api.model
    def make_todo_test(self):
        if not ast.literal_eval(self.env['ir.config_parameter'].get_param('runbot.record.test', 'False')):
            raise UserError('Must be recording a test flow')
        return {
            'name': 'Record test to do',
            'type': 'ir.actions.act_window',
            'res_model': 'runbot.record.test',
            'views': [[False, 'form']],
            'view_mode': 'form',
            'context': self.env.context,
            'target': 'new',
        }

    @api.model
    def stop_registration(self):
        self.env['ir.config_parameter'].set_param('runbot.record.test', 'False')
        self.env['ir.config_parameter'].set_param('runbot.record.demo', 'False')
        self.env['ir.config_parameter'].set_param('runbot.record.current', '')


    @api.model
    def get_runbot_start_test(self):
        return ast.literal_eval(self.env['ir.config_parameter'].get_param('runbot.record.test', 'False'))

    @api.model
    def get_runbot_start_demo(self):
        return ast.literal_eval(self.env['ir.config_parameter'].get_param('runbot.record.demo', 'False'))

    def write(self, vals):
        # Write only on record of same type to be sure it works
        if 'content' in vals and 'test' in self.mapped('record_type'):
            vals['content'] = self._format_python(vals['content'])
        res = super(RunbotRecording, self).write(vals)
        return res

    @api.model
    def create(self, vals):
        if 'content' in vals and vals.get('record_type') != 'demo':
            vals['content'] = self._format_python(vals['content'])
        res = super(RunbotRecording, self).create(vals)
        return res

    def _format_python(self, content):
        return autopep8.fix_code(content, options={'aggressive': 1}) if content else ''

class RunbotRecordingLine(models.Model):
    _name = 'runbot.record.line'
    _description = 'Runbot test lines'
    _rec_name = 'description'
    _order = 'sequence'

    record_id = fields.Many2one(
        'runbot.record',
        string='Recording',
    )
    description = fields.Text(string='Description')
    sequence = fields.Integer(string='Sequence')

class RunbotRecordingReferencedRecord(models.Model):
    _name = 'runbot.record.reference'
    _description = 'Runbot test references'
    _order = 'id desc'

    record_id = fields.Many2one(
        'runbot.record',
        string='Recording',
    )
    res_id = fields.Integer(
        string='Reference id',
    )
    res_model = fields.Char(
        string='Reference model',
    )
    reference = fields.Char(
        string='Reference',
    )
