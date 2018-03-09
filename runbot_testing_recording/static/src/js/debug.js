odoo.define('runbot_testing_recording.DebugManager', function (require) {
"use strict";

var core = require("web.core");
var DebugManager = require('web.DebugManager');
var Dialog = require("web.Dialog");
var Model = require('web.Model');


function is_runbot_start_test_registration () {
            var _this = this
            new Model('runbot.record').call('get_runbot_start_test').then(function(runbot_start_test) {
                _this.runbot_start_test = runbot_start_test;
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
        this.runbot_start_test = _.bind(is_runbot_start_test_registration, this)();
        this.runbot_start_demo = _.bind(is_runbot_start_demo_registration, this)();
        return this._super.apply(this, arguments);
    },
    runbot_start_test_registration: function() {
        var _this = this;
        var Record = new Model('runbot.record');
        Record.call('open_registration', [{'default_record_type': 'test'}]).then(function(act) {
                    _this.do_action(act);
                });
        this.runbot_start_test = true;
        this.update()
    },
    runbot_start_demo_registration: function() {
        var _this = this;
        var Record = new Model('runbot.record');
        Record.call('open_registration', [{'default_record_type': 'demo'}]).then(function(act) {
                    _this.do_action(act);
                });;
        this.runbot_start_demo = true;
        this.update()
    },
    runbot_make_todo_test: function() {
        var _this = this;
        var Record = new Model('runbot.record');
        Record.call('make_todo_test', [this._context]).then(function(act) {
                    _this.do_action(act);
                });;
    },
    runbot_stop_registration: function() {
        var Record = new Model('runbot.record');
        Record.call('stop_registration', [this._context]);
        this.runbot_start_test = false;
        this.runbot_start_demo = false;
        this.update()
    },
});

});
