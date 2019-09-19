odoo.define('runbot_testing_recording.DebugManager', function (require) {
"use strict";

var core = require("web.core");
var DebugManager = require('web.DebugManager');
var Dialog = require("web.Dialog");
var rpc = require('web.rpc');
var ajax = require('web.ajax');
var _lt = core._lt;
var utils = require('web.utils');
var time = require('web.time');
var CrashManager = require('web.CrashManager').CrashManager;

var is_runbot_start_test_registration_variable

var map_title ={
    user_error: _lt('Warning'),
    warning: _lt('Warning'),
    access_error: _lt('Access Error'),
    missing_error: _lt('Missing Record'),
    validation_error: _lt('Validation Error'),
    access_denied: _lt('Access Denied'),
};

var genericJsonRpc = function (fct_name, params, settings, fct) {
    var shadow = settings.shadow || false;
    delete settings.shadow;
    if (!shadow) {
        core.bus.trigger('rpc_request');
    }

    var data = {
        jsonrpc: "2.0",
        method: fct_name,
        params: params,
        id: Math.floor(Math.random() * 1000 * 1000 * 1000)
    };
    var xhr = fct(data);
    var result = xhr.then(function(result) {
        core.bus.trigger('rpc:result', data, result);
        if (result.error !== undefined) {
            if (result.error.data.arguments[0] !== "bus.Bus not available in test mode") {
                console.debug(
                    "Server application error\n",
                    "Error code:", result.error.code, "\n",
                    "Error message:", result.error.message, "\n",
                    "Error data message:\n", result.error.data.message, "\n",
                    "Error data debug:\n", result.error.data.debug
                );
            }
            return Promise.reject({type: "server", error: result.error});
        } else {
            return result.result;
        }
    }, function() {
        //console.error("JsonRPC communication error", _.toArray(arguments));
        var reason = {
            type: 'communication',
            error: arguments[0],
            textStatus: arguments[1],
            errorThrown: arguments[2],
        };
        return Promise.reject(reason);
    });

    var rejection;
    var promise = new Promise(function (resolve, reject) {
        rejection = reject;

        result.then(function (result) {
            if (!shadow) {
                core.bus.trigger('rpc_response');
            }
            resolve(result);
        }, function (reason) {
            var type = reason.type;
            var error = reason.error;
            var textStatus = reason.textStatus;
            var errorThrown = reason.errorThrown;
            if (type === "server") {
                if (!shadow) {
                    core.bus.trigger('rpc_response');
                }
                if (error.code === 100) {
                    core.bus.trigger('invalidate_session');
                }
                reject({message: error, event: $.Event()});
            } else {
                if (!shadow) {
                    core.bus.trigger('rpc_response_failed');
                }
                var nerror = {
                    code: -32098,
                    message: "XmlHttpRequestError " + errorThrown,
                    data: {
                        type: "xhr"+textStatus,
                        debug: error.responseText,
                        objects: [error, errorThrown]
                    },
                };
                reject({message: nerror, event: $.Event()});
            }
        });
    });

    // FIXME: jsonp?
    promise.abort = function () {
        rejection({
            message: "XmlHttpRequestError abort",
            event: $.Event('abort')
        });
        if (xhr.abort) {
            xhr.abort();
        }
    };
    promise.guardedCatch(function (reason) { // Allow promise user to disable rpc_error call in case of failure
        setTimeout(function () {
            // we want to execute this handler after all others (hence
            // setTimeout) to let the other handlers prevent the event
            if (!reason.event.isDefaultPrevented()) {
                core.bus.trigger('rpc_error', reason.message, reason.event, params);
                //NOTE: Inject params to be used inside downstream
                //      processing.
                //      See CrashManager extension down this same
                //      file, inside the call to do_action the
                //      error_caught_params context's key.
            }
        }, 0);
    });
    return promise;
};

var jsonRpc = function (url, fct_name, params, settings) {
        settings = settings || {};
        return genericJsonRpc(fct_name, params, settings, function (data) {
            return $.ajax(url, _.extend({}, settings, {
                url: url,
                dataType: 'json',
                type: 'POST',
                data: JSON.stringify(data, time.date_to_utc),
                contentType: 'application/json'
            }));
        });
    }
ajax.jsonRpc = jsonRpc;

function is_runbot_start_test_registration () {
    var _this = this
    ajax.genericJsonRpc = genericJsonRpc;
    rpc.query({
        model: 'runbot.record',
        method: 'get_runbot_start_test',
        args: [],
    }).then(function(runbot_start_test) {
        _this.runbot_start_test = runbot_start_test;
        is_runbot_start_test_registration_variable = runbot_start_test;
    });
    return this.runbot_start_test
}

function is_runbot_start_demo_registration () {
    var _this = this
    ajax.genericJsonRpc = genericJsonRpc;
    rpc.query({
        model: 'runbot.record',
        method: 'get_runbot_start_demo',
        args: [],
    }).then(function(runbot_start_demo) {
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
        rpc.query({
            model: 'runbot.record',
            method: 'open_registration',
            context: {'default_record_type': 'test'},
        }).then(function(act) {
            _this.do_action(act);
            _this.runbot_start_test = true;
            is_runbot_start_test_registration_variable = true
            _this.update();
        });
    },
    runbot_start_demo_registration: function() {
        var _this = this;
        rpc.query({
            model: 'runbot.record',
            method: 'open_registration',
            context: {'default_record_type': 'demo'},
        }).then(function(act) {
            _this.do_action(act);
            _this.runbot_start_demo = true;
            _this.update();
        });
    },
    runbot_make_todo_test: function() {
        var _this = this;
        var context = {}
        if (this._context) {
            context = this._context;
        }
        rpc.query({
            model: 'runbot.record',
            method: 'make_todo_test',
            context: context,
        }).then(function(act) {
            _this.do_action(act);
        });
    },
    runbot_stop_registration: function() {
        rpc.query({
            model: 'runbot.record',
            method: 'stop_registration',
            context: this._context || {},
        });
        this.runbot_start_test = false;
        is_runbot_start_test_registration_variable = false
        this.runbot_start_demo = false;
        this.update();
    },
});

CrashManager.include({
    rpc_error: function (error) {
        var self = this
        if (is_runbot_start_test_registration_variable && _.has(map_title, error.data.exception_type)) {
            self.do_action({
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
});
