odoo.define('runbot_testing_recording.DebugManager', function (require) {
"use strict";

var core = require("web.core");
var DebugManager = require('web.DebugManager');
var Dialog = require("web.Dialog");
var Model = require('web.Model');
var ajax = require('web.ajax');
var _lt = core._lt;

var is_runbot_start_test_registration_variable

var map_title ={
    user_error: _lt('Warning'),
    warning: _lt('Warning'),
    access_error: _lt('Access Error'),
    missing_error: _lt('Missing Record'),
    validation_error: _lt('Validation Error'),
    access_denied: _lt('Access Denied'),
};

function is_runbot_start_test_registration () {
            var _this = this
            new Model('runbot.record').call('get_runbot_start_test').then(function(runbot_start_test) {
                _this.runbot_start_test = runbot_start_test;
                is_runbot_start_test_registration_variable = runbot_start_test;
            });
            return this.runbot_start_test
}
function is_runbot_start_demo_registration () {
            var _this = this
            new Model('runbot.record').call('get_runbot_start_demo').then(function(runbot_start_demo) {
                _this.runbot_start_demo = runbot_start_demo;
            });
            return this.runbot_start_test
}

DebugManager.include({
    start: function () {
        if (!(this.getParent() instanceof Dialog)) {
            this.runbot_start_test = _.bind(is_runbot_start_test_registration, this)();
            this.runbot_start_demo = _.bind(is_runbot_start_demo_registration, this)();
        }
        return this._super.apply(this, arguments);
    },
    runbot_start_test_registration: function() {
        var _this = this;
        var Record = new Model('runbot.record');
        Record.call('open_registration', [{'default_record_type': 'test'}]).then(function(act) {
                    _this.do_action(act);
                    _this.runbot_start_test = true;
                    is_runbot_start_test_registration_variable = true
                    _this.update();
                });
    },
    runbot_start_demo_registration: function() {
        var _this = this;
        var Record = new Model('runbot.record');
        Record.call('open_registration', [{'default_record_type': 'demo'}]).then(function(act) {
                    _this.do_action(act);
                    _this.runbot_start_demo = true;
                    _this.update();
                });
    },
    runbot_make_todo_test: function() {
        var _this = this;
        var Record = new Model('runbot.record');
        var context = {}
        if (this._context) {
            context = this._context;
        }
        Record.call('make_todo_test', [context]).then(function(act) {
                    _this.do_action(act);
                });;
    },
    runbot_stop_registration: function() {
        var Record = new Model('runbot.record');
        var context = {}
        if (this._context) {
            context = this._context;
        }
        Record.call('stop_registration', [context]);
        this.runbot_start_test = false;
        is_runbot_start_test_registration_variable = false
        this.runbot_start_demo = false;
        this.update();
    },
});

var CrashManager = require('web.CrashManager');
var Session = require('web.Session');
var web_client = require('web.web_client');

CrashManager.include({
    rpc_error: function (error) {
        if (is_runbot_start_test_registration_variable && _.has(map_title, error.data.exception_type)) {
            web_client.do_action({
                res_model: 'runbot.record.error',
                name: 'Error Caught',
                type: 'ir.actions.act_window',
                views: [[false, 'form']],
                view_mode: 'form',
                target: 'new',
                context: {
                    'default_error_type': error.data.name,
                    'default_description': error.data.arguments[0],
                    'error_caught_params': arguments[2]
                    }
            });
        } else {
            return this._super.apply(this, arguments);
            
        };
    },
});

Session.include({
    rpc: function(url, params, options) {
        var self = this;
        options = _.clone(options || {});
        var shadow = options.shadow || false;
        options.headers = _.extend({}, options.headers)
        if (odoo.debug) {
            options.headers["X-Debug-Mode"] = $.deparam($.param.querystring()).debug;
        }

        delete options.shadow;

        return self.check_session_id().then(function() {
            // TODO: remove
            if (! _.isString(url)) {
                _.extend(options, url);
                url = url.url;
            }
            // TODO correct handling of timeouts
            if (! shadow)
                self.trigger('request');
            var fct;
            if (self.origin_server) {
                fct = ajax.jsonRpc;
                if (self.override_session) {
                    options.headers["X-Openerp-Session-Id"] = self.session_id || '';
                }
            } else if (self.use_cors) {
                fct = ajax.jsonRpc;
                url = self.url(url, null);
                options.session_id = self.session_id || '';
                if (self.override_session) {
                    options.headers["X-Openerp-Session-Id"] = self.session_id || '';
                }
            } else {
                fct = ajax.jsonpRpc;
                url = self.url(url, null);
                options.session_id = self.session_id || '';
            }
            var p = fct(url, "call", params, options);
            p = p.then(function (result) {
                if (! shadow)
                    self.trigger('response');
                return result;
            }, function(type, error, textStatus, errorThrown) {
                if (type === "server") {
                    if (! shadow)
                        self.trigger('response');
                    if (error.code === 100) {
                        self.uid = false;
                    }
                    return $.Deferred().reject(error, $.Event());
                } else {
                    if (! shadow)
                        self.trigger('response_failed');
                    var nerror = {
                        code: -32098,
                        message: "XmlHttpRequestError " + errorThrown,
                        data: {type: "xhr"+textStatus, debug: error.responseText, objects: [error, errorThrown] }
                    };
                    return $.Deferred().reject(nerror, $.Event());
                }
            });
            return p.fail(function() { // Allow deferred user to disable rpc_error call in fail
                p.fail(function(error, event) {
                    if (!event.isDefaultPrevented()) {
                        self.trigger('error', error, event, params);
                    }
                });
            });
        });
    },
})

});
