# -*- coding: utf-8 -*-
from lxml import etree, html
import pprint
import re
import uuid
from copy import deepcopy

from odoo.http import request
from odoo.addons.web.controllers.main import DataSet
from odoo.models import BaseModel
from odoo import models, fields, api, _, SUPERUSER_ID
from odoo.exceptions import UserError
from odoo.tools import ustr

ODOO_TAG_VERSION = '10.0e'
XML_TYPE_MODEL_FIELDS = [
    ('ir.ui.view', 'arch')
]
METHOD_TO_AVOID = [
    'make_todo_test',
    'start_test_registration',
    'stop_test_registration',
    'start_demo_registration',
    'stop_demo_registration',
    ]

MODEL_TO_AVOID = [
    'runbot.record',
    'runbot.record.test',
    'runbot.record.line',
    'runbot.record.error',
    ]

METHODS_FOR_DEMO_DATA = [
    'create',
    'name_create',
    'write',
    'copy',
    'unlink',
    ]

CREATED_IDS = {}

class ReportDataset(DataSet):
    def _call_kw(self, model, method, args, kwargs):
        global CREATED_IDS
        CREATED_IDS = {}
        request.cr.method_is_writing_in_db = False
        update_vals(method, args, kwargs)
        prepare_record_to_unlink(model, method, args)
        copy_args = deepcopy(args)
        copy_kwargs = deepcopy(kwargs)
        result =  super(ReportDataset, self)._call_kw(model, method, args, kwargs)
        save_call(model, method, result, copy_args, copy_kwargs)
        request.cr.method_is_writing_in_db = False
        return result

class Base(models.AbstractModel):
    _inherit = 'base'

    @api.model
    def create(self, vals):
        global CREATED_IDS
        unique_hash_key = False
        if 'unique_hash_key' in vals:
            unique_hash_key = vals.pop('unique_hash_key')
        res = super(Base, self).create(vals)
        if unique_hash_key:
            xml_id = generate_xml_id(res.id, self._name, test_type='demo')
            CREATED_IDS[unique_hash_key] = {
                'res_id': res.id,
                'model': self._name,
                'xml_id': generate_xml_id(res.id, self._name, test_type='demo'),
                'complete_vals': vals,
                }
        return res

def update_vals(method, args, kwargs):
    def add_key(vals):
        key = uuid.uuid4().hex
        vals['unique_hash_key'] = key
        for k, v in vals.items():
            if isinstance(v, list):
                for element in v:
                    if element and (isinstance(element, tuple) or isinstance(element, list)) and element[0] == 0:
                        add_key(element[2])
    runbot_demo = eval(request.env['ir.config_parameter'].sudo().get_param('runbot.record.demo', 'False'))
    if runbot_demo and method in METHODS_FOR_DEMO_DATA and method != 'unlink':
        values = None
        if method == 'write':
            values = args[1]
        if method == 'create':
            values = args[0]
        if values:
            add_key(values)

def prepare_record_to_unlink(model, method, args):
    runbot_demo = eval(request.env['ir.config_parameter'].sudo().get_param('runbot.record.demo', 'False'))
    global CREATED_IDS
    if runbot_demo and method == 'unlink':
        CREATED_IDS['delete_ids'] = []
        ids, values = args[0], args[1]
        for id in ids:
            xml_id = generate_xml_id(id, model, test_type='demo', create_if_not_found=False)
            if xml_id:
                CREATED_IDS['delete_ids'].append(xml_id)
            # TODO: what to do if record has no xml_id?

def save_call(model, method, result, args, kwargs):
    runbot_test = eval(request.env['ir.config_parameter'].sudo().get_param('runbot.record.test', 'False'))
    runbot_demo = eval(request.env['ir.config_parameter'].sudo().get_param('runbot.record.demo', 'False'))
    if model in MODEL_TO_AVOID or method in METHOD_TO_AVOID:
        return
    if (runbot_test and request.cr.method_is_writing_in_db) or \
        (runbot_demo and method in METHODS_FOR_DEMO_DATA):
        recording_id = get_current_test()
        if recording_id:
            if runbot_test:
                content = format_python(model, method, args, kwargs, result=result)
            if runbot_demo:
                if method ==  'copy':
                    raise UserError(_('Avoid duplicating record when recording demonstration data'))
                content = format_python_xml(model, method, args, kwargs, result)
            content = '\n'.join([recording_id.content or '', content])
            recording_id.content = content

def find_links(origin, target):
    max_depth = 2
    already_looked = {}
    final_result = []
    def find_path(origin, target, depth, path):
        for fieldname, field in origin._fields.items():
            if depth == max_depth:
                continue
            if field.type not in ['many2one', 'many2many', 'one2many']:
                continue
            if (origin._name, fieldname) in already_looked:
                # print 'already found'
                copy_path = deepcopy(path)
                final_result.append(copy_path + already_looked[(origin._name, fieldname)])
            if field.comodel_name == target._name:
                copy_path = deepcopy(path)
                copy_path.append((origin._name,fieldname))
                final_result.append(copy_path)
                # already_looked[((origin._name, fieldname))] = result
            copy_path = deepcopy(path)
            copy_path.append((origin._name,fieldname))
            find_path(origin[:1][fieldname], target, depth+1, copy_path)
    find_path(origin, target, 1, [])

    paths = [('.'.join([y[1]for y in x]), len(x))for x in final_result]

    result = []
    for path, length in paths:
        if target in origin.mapped(path):
            result.append((path, length))
    result = sorted(result, key=lambda r: r[1])
    result[:5]
    return [x[0] for x in result]


def format_python(model_name, method_name, args, kwargs, result=None):
    fields_to_replace_in_context = []
    args_to_replace = {}
    stack_pre_call = []
    stack_post_call = []
    env_call = ''
    context_call = ''
    def append_call(variable_name, element, todo, replace_in_context):
        element_output = '%s = %s' % (variable_name, element)
        if todo:
            stack_pre_call.append('# TODO: Check or Find %s link (external id or otherwise)' % (variable_name))
        stack_pre_call.append(element_output)
        if replace_in_context:
            fields_to_replace_in_context.append(variable_name)

    model = request.env[model_name].sudo()
    method = getattr(type(model), method_name)

    # Object calling
    if getattr(method, '_api', None) in ['model', 'model_create']:
        if method_name in ['create', 'name_create']:
            env_call = 'record = self.env[\'%s\']' % (model._name)
        else:
            env_call = 'self.env[\'%s\']' % (model._name)
    else:
        ids, args = args[0], args[1:]
        ids_name, todo_ids = get_env_ref_multi(ids, model_name)
        if method_name == 'copy':
            append_call('record_ids', ids_name, todo_ids, False)
            env_call ='record = self.env[\'%s\'].browse(record_ids)' % (model._name)
        else:
            append_call('record_ids', ids_name, todo_ids, False)
            env_call = 'self.env[\'%s\'].browse(record_ids)' % (model._name)
    # Context
    context, args, kwargs = api.split_context(method, args, kwargs)
    if context and 'active_id' in context:
        active_id_name, todo_active_id = get_env_ref_single(context['active_id'], context['active_model'])
        append_call('active_id', active_id_name, todo_active_id, True)
        active_ids_name,todo_active_ids = get_env_ref_multi(context['active_ids'], context['active_model'])
        append_call('active_ids', active_ids_name, todo_active_ids, True)

    # Sudo
    sudo_name=''
    if context:
        user_id_name, todo_user_id = get_env_ref_single(context['uid'], 'res.users')
        append_call('uid', user_id_name, todo_user_id, True)
        if context.get('uid') != SUPERUSER_ID:
            sudo_name = '.sudo(uid)'

    if context:
        for field in fields_to_replace_in_context:
            context[field] = 'FIELD_%s_TO_REPLACE' % field
        context_call = '.with_context(%s)' % pprint.pformat(context)
        for field in fields_to_replace_in_context:
            context_call = context_call.replace("u'FIELD_%s_TO_REPLACE'" % field, field)
            context_call = context_call.replace("'FIELD_%s_TO_REPLACE'" % field, field)

    # args and kwargs
    if method_name in ['create', 'write']:
        args[0] = add_groups_values(model_name, args[0])
        replace_idtoxml(model_name, args[0], args_to_replace)
        for field in args_to_replace:
            args[0][field] = 'FIELD_%s_TO_REPLACE' % field
    args_name = ', '.join(['\'%s\'' % a if isinstance(a, str) else '%s' % ustr(a) for a in args]) 
    for field in args_to_replace:
        args_name = args_name.replace("u'FIELD_%s_TO_REPLACE'" % field, args_to_replace[field])
        args_name = args_name.replace("'FIELD_%s_TO_REPLACE'" % field, args_to_replace[field])
    kwargs_name = ', '.join(['%s=%s' % (k,'\'%s\'' % kwargs[k] if isinstance(kwargs[k], str) else '%s' % ustr(kwargs[k])) for k in kwargs])
    args_name += ', %s' % (kwargs_name) if kwargs_name else ''
    method_call = '%s%s%s.%s(%s)' % (env_call, context_call, sudo_name, method_name, args_name) 
    if method_name in ['create', 'copy', 'name_create'] and result:
        if method_name == 'name_create':
            result = result[0]
        stack_post_call.append(generate_xml_id(result, model_name, result_name='record'))

    # CONCATENATION
    return format_call_stack(stack_pre_call, stack_post_call, method_call)

def format_call_stack(stack_pre_call, stack_post_call, method_call):
    call = method_call
    if stack_pre_call:
        pre_call = '\n'.join(stack_pre_call)
        call = '%s\n%s' % (pre_call, call)
    if stack_post_call:
        post_call = '\n'.join(stack_post_call)
        call = '%s\n%s' % (call, post_call)
    return call

def generate_xml_id(rec_id, rec_model, result_name=None, test_type='test', create_if_not_found=True):
    ir_model_data = request.env['ir.model.data'].sudo()
    module_name = get_module_name()
    data = ir_model_data.search([('model', '=', rec_model), ('res_id', '=', rec_id)])
    if not data and not create_if_not_found:
        return False
    if not data and create_if_not_found:
        postfix = 0
        test_name = re.sub('[^a-zA-Z]+', '', get_current_test().name).lower()
        name = '%s_%s_%s' % (test_name, request.env[rec_model].sudo()._table, rec_id)
        while ir_model_data.search([('module', '=', module_name), ('name', '=', name)]):
            postfix += 1
            name = '%s_%s_%s' % (request.env[rec_model].sudo()._table, rec_id, postfix)
        values = {
            'model': rec_model,
            'res_id': rec_id,
            'module': module_name,
            'name': name,
        }
        data = ir_model_data.create(values)
        get_current_test().write({
            'reference_ids':[(0,0,{
                'res_id': rec_id,
                'res_model': rec_model,
                'reference': 'self.env.ref(\'%s.%s\')' % (module_name, name),
                })],
            })
    if test_type == 'demo':
        return data.complete_name

    values = {
        'model': data.model,
        'res_id': 'RES_ID_TO_CHANGE',
        'module': data.module,
        'name': data.name,
    }
    values = pprint.pformat(values)
    values = values.replace("'RES_ID_TO_CHANGE'", '%s.id' % result_name)
    return 'self.env[\'ir.model.data\'].create(%s)' % (values)

def get_record(rec_id, model):
    return request.env[model].sudo().search([('id','=',rec_id)])

def get_current_test():
    rec_id = int(request.env['ir.config_parameter'].sudo().get_param('runbot.record.current', '0'))
    rec = request.env['runbot.record'].sudo().browse(rec_id)
    return rec

def get_module_name():
    rec = get_current_test()
    return rec.module_id.name

def get_xml_id(res_id, model):
    data = request.env['ir.model.data'].sudo().search([
        ('res_id','=',res_id),
        ('model','=',model),
        ], limit=1)
    if data:
        if data.module:
            return '%s.%s' % (data.module, data.name)
        else:
            return data.name

def get_env_ref_multi(ids, model_name):
    todo = False
    result = '['
    if not isinstance(ids, list):
        ids = [ids]
    for id in ids:
        rename, todo_single = get_env_ref_single(id, model_name)
        result += '%s,' % rename
        todo = todo or todo_single
    result += ']'
    return result, todo

def get_env_ref_single(id, model_name):
    if get_xml_id(id, model_name):
        result = 'self.env.ref(\'%s\').id' % get_xml_id(id, model_name)
        todo = False
    else:
        current_test = get_current_test()
        if current_test.reference_ids:
            if current_test.reference_ids.filtered(lambda r: r.res_model==model_name and r.res_id==id):
                result = '%s.id' % (current_test.reference_ids.filtered(lambda r: r.res_model==model_name and r.res_id==id)[:1].reference)
                todo = True
                return result, todo
            ref = current_test.reference_ids[:1]
            links = find_links(request.env[ref.res_model].sudo().browse(ref.res_id), request.env[model_name].sudo().browse(id))
            if links:
                # TODO: keep other links and store it somewhere?
                result = '%s.%s.id' % (ref.reference, links[0])
                current_test.write({
                    'reference_ids': [(0,0,{
                        'res_id': id,
                        'res_model': model_name,
                        'reference': '%s.%s' % (ref.reference, links[0]),
                        })],
                    })
                todo = True
                return result, todo
        result = '%s' % id
        todo = True
    return result, todo

def get_values_from_context(model, context):
    output = {}
    for fieldname in model._fields:
        key = 'default_' + fieldname
        if key in context:
            output[fieldname] = context[key]
    return output

def clean_default_value(model, values):
    for fieldname in model._fields:
        if fieldname in values:
            field = model._fields[fieldname]
            if field.default:
                if callable(field.default):
                    if field.type == 'many2one' and isinstance(field.default(model), models.Model) and field.default(model).id == values[fieldname]:
                        values.pop(fieldname)
                        continue
                    if field.default(model) == values[fieldname]:
                        values.pop(fieldname)
                        continue
                elif field.default == values[fieldname]:
                    values.pop(fieldname)
                    continue
            if not field.default and ((not values[fieldname] or values[fieldname] == [(6,0,[])]) == (not field.default)):
                values.pop(fieldname)
                continue

def replace_idtoxml(model_name, values, args_to_replace):
    model = request.env[model_name].sudo()
    for fieldname in values:
        if fieldname not in model._fields:
            continue
        value = values[fieldname]
        field = model._fields[fieldname]
        if field.type != 'many2one':
            continue
        ir_model_data = request.env['ir.model.data'].sudo()
        data = ir_model_data.search([('model', '=', field.comodel_name), ('res_id', '=', value)], limit=1)
        if data:
            args_to_replace[fieldname] = 'self.env.ref(\'%s.%s\').id' % (data.module, data.name)

def add_groups_values(model_name, values):
    if model_name != 'res.users':
        return values
    return request.env[model_name].sudo()._remove_reified_groups(values)


def format_python_xml(model_name, method_name, args, kwargs, result):
    global CREATED_IDS
    data_to_format = []
    data_formated = []
    data_to_xml = []
    model = request.env[model_name].sudo()
    method = getattr(type(model), method_name)
    if getattr(method, '_api', None) in ['model', 'model_create']:
        ids = []
        vals = args[0]
    else:
        ids, args = args[0], args[1:]
        vals = args[0]
    context, args, kwargs = api.split_context(method, args, kwargs)
    if method_name ==  'unlink':
        for xml_id in CREATED_IDS['delete_ids']:
            data_to_format.append((xml_id,{}, model_name, method_name))
    if method_name == 'write':
        values = add_groups_values(model_name, vals)
        for id in ids:
            xml_id = generate_xml_id(id, model_name, test_type='demo')
            data_to_format.append((xml_id,values, model_name, method_name))
    if method_name in ['create', 'name_create']:
        values = get_values_from_context(model, context)
        if method_name == 'name_create':
            values[model._rec_name] = vals
            result = result[0]
        else:
            values.update(vals)
        values = add_groups_values(model_name, values)
        xml_id = generate_xml_id(result, model_name, test_type='demo')
        data_to_format.append((xml_id,values, model_name, 'create'))

    while data_to_format:
        xml_id, vals, modelname, methodname = data_to_format.pop(0)
        formated_element = generate_formated_element(xml_id, vals, modelname, methodname, data_to_format)
        if formated_element:
            data_formated.append(formated_element)

    for element in data_formated:
        xml_id, vals, modelname, methodname = element
        data_to_xml.append(generate_xml_element(xml_id, vals, modelname, methodname))

    return '\n'.join(data_to_xml)

def generate_formated_element(xml_id, values, model_name, method_name, data_to_format):
    global CREATED_IDS
    do_again = False
    xml_id_not_found = xml_id.split('.')[0] == 'TODO'
    if xml_id_not_found:
        res_id = int(xml_id.split('.')[2])
    model = request.env[model_name].sudo()
    orgin_record = (xml_id, values, model_name, method_name)
    if method_name in  ['create', 'copy']:
        clean_default_value(model, values)
    for fieldname in values:
        if fieldname == 'unique_hash_key' or fieldname not in model._fields:
            continue
        value = values[fieldname]
        field = model._fields[fieldname]

        if field.type in ['one2many', 'many2many']:
            magic_output = []
            idx = 0
            idx_to_remove = []
            for magic_tuple in value:
                idx += 1
                if magic_tuple[0] == 0:
                    sub_value = magic_tuple[2]
                    if field.type == 'one2many':
                        sub_value[field.inverse_name] = request.env.ref(xml_id).sudo().id if not xml_id_not_found else res_id
                    current_record = CREATED_IDS[sub_value['unique_hash_key']]
                    record_to_create = (current_record['xml_id'], sub_value, field.comodel_name, 'create')
                    if field.type == 'one2many':
                        data_to_format.append(record_to_create)
                        idx_to_remove.append(idx-1)
                    else:
                        value[idx -1] = (4, current_record['res_id'], 0)
                        data_to_format.insert(0, orgin_record)
                        data_to_format.insert(0, record_to_create)
                        do_again = True
                if magic_tuple[0] == 1:
                    new_xml_id = generate_xml_id(magic_tuple[1], field.comodel_name, test_type='demo', create_if_not_found=False)
                    if not new_xml_id:
                        new_xml_id = 'TODO.find_xml_id.%s' % magic_tuple[1]
                    data_to_format.insert(0, orgin_record)
                    data_to_format.append((new_xml_id, magic_tuple[2], field.comodel_name, 'write'))
                    idx_to_remove.append(idx-1)
                    do_again = True
            for idx in sorted(idx_to_remove, reverse=True):
                value.pop(idx)
    if do_again:
        return None
    return (xml_id, values, model_name, method_name)


def generate_xml_element(xml_id, values, model_name, method_name):
    xml_id_not_found = xml_id.split('.')[0] == 'TODO'
    if xml_id_not_found:
        res_id = int(xml_id.split('.')[2])
    mod = request.env[model_name].sudo()
    record_type = 'record' if method_name != 'unlink' else 'delete'
    xml_record = etree.Element(record_type, attrib={
        'id': xml_id,
        'model': mod._name
    })
    for fieldname in values:
        if fieldname == 'unique_hash_key' or (fieldname not in mod._fields and fieldname not in values):
            continue
        xml_field = etree.SubElement(xml_record, 'field', attrib={
            'name': fieldname,
        })
        value = values[fieldname]
        if fieldname not in mod._fields:
            xml_field.set('TODO', 'Warning, non exiting field in write or create')
            xml_field.text = '%s' % value
            continue
        field = mod._fields[fieldname]

        if field.type == 'boolean':
            xml_field.set('eval', ustr(value))
        elif field.type in ['many2one', 'reference']:

            if field.type == 'many2one':
                comodel_name = field.comodel_name
                comodel_id = value
            else:
                vals = value.split(',')
                comodel_name = vals[0]
                comodel_id = vals[1]
            new_xml_id = generate_xml_id(comodel_id, comodel_name, test_type='demo', create_if_not_found=False)
            if new_xml_id:
                xml_field.set('ref', new_xml_id)
            else:
                xml_field.set('TODO', 'find the external id')
                xml_field.set('eval', '%s' % value)
        elif field.type in ['one2many', 'many2many']:
            magic_output = []
            for magic_tuple in value:
                if magic_tuple[0] in (2, 3, 4):
                    new_xml_id = generate_xml_id(magic_tuple[1], field.comodel_name, test_type='demo', create_if_not_found=False)
                    if new_xml_id:
                        magic_output.append('(%s, ref(\'%s\'), 0)' % (magic_tuple[0], new_xml_id))
                    else:
                        magic_output.append('(%s, %s, %s)' % (magic_tuple[0], magic_tuple[1]))
                        xml_field.set('TODO', 'find the external id')
                if magic_tuple[0] == 5:
                    magic_output.append('(5,0,0)')
                if magic_tuple[0] == 6:
                    output_list = []
                    for element in magic_tuple[2]:
                        new_xml_id = generate_xml_id(element, field.comodel_name, test_type='demo', create_if_not_found=False)
                        if new_xml_id:
                            output_list.append('ref(\'%s\')' % new_xml_id)
                        else:
                            output_list.append('%s' % element)
                            xml_field.set('TODO', 'find the external id')
                    magic_output.append('(6, 0, [%s])' % ', '.join(['%s' % x for x in output_list]))
            if magic_output:
                xml_field.set('eval', '[%s]' % ', '.join(magic_output))
            else: 
                xml_record.remove(xml_field)
        elif (mod._name, fieldname) in XML_TYPE_MODEL_FIELDS:
            xml_field.set('type', 'xml')
            xml_field.append(etree.XML(value))
        elif field.type in ['html']:
            xml_field.set('type', 'html')
            xml_field.append(html.fromstring(value))
        elif field.type in ['text']:
            if value:
                field_text = ustr(value)
                xml_field.text = etree.CDATA('\n%s\n' % field_text)
        else:
            if value:
                xml_field.text = ustr(value)
    return etree.tostring(xml_record, pretty_print=True)
