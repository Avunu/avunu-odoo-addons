// Copyright 2026 Avunu LLC (avu.nu)
// License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import { Component, onWillDestroy, useExternalListener, useState } from "@odoo/owl";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { useDropdownState } from "@web/core/dropdown/dropdown_hooks";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const { DateTime } = luxon;

const TIMER_CHANGED = "hr_timesheet_time_control_systray.timer_changed";

/**
 * The running timesheet timer, counting up, in the navbar.
 *
 * project_timesheet_time_control can start and stop a timer from a record,
 * but the running line is only ever visible by navigating to it, and its
 * duration stays 0:00 until it is stopped. This puts the elapsed time on
 * every screen and makes stopping reachable from all of them.
 */
export class TimesheetTimerSystray extends Component {
    static components = { Dropdown };
    static props = [];
    static template = "hr_timesheet_time_control_systray.TimesheetTimerSystray";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.busService = useService("bus_service");
        this.dropdown = useDropdownState();

        this.state = useState({
            // Nothing renders until the server has said this user is a
            // timesheet user, so non-timesheet users never see it flash.
            enabled: false,
            timer: false,
            runningCount: 0,
            elapsed: 0,
            stopping: false,
        });

        // Difference between the server clock and this browser's, in ms. A
        // shop floor tablet with a drifted clock would otherwise show a timer
        // that is wrong by that drift, or counting up from the future.
        this.clockOffset = 0;

        this.onTimerChanged = () => this.load();
        this.busService.subscribe(TIMER_CHANGED, this.onTimerChanged);
        this.busService.start();

        // Belt and braces for the case where the websocket never came up
        // (blocked, or a proxy that drops it): coming back to the tab is
        // exactly when a stale timer would be noticed.
        useExternalListener(window, "focus", () => this.load());

        this.interval = setInterval(() => this.tick(), 1000);

        onWillDestroy(() => {
            clearInterval(this.interval);
            this.busService.unsubscribe(TIMER_CHANGED, this.onTimerChanged);
        });

        // Not awaited: the navbar must not wait on this to paint. Same as
        // core's attendance menu.
        this.load();
    }

    async load() {
        const data = await this.orm.call("account.analytic.line", "get_running_timer", []);
        this.state.enabled = data.enabled;
        if (!data.enabled) {
            this.state.timer = false;
            return;
        }
        this.clockOffset = deserializeDateTime(data.server_time).ts - Date.now();
        this.state.timer = data.timer;
        this.state.runningCount = data.running_count;
        this.tick();
    }

    /** Recompute elapsed seconds. Cheap enough to run every second. */
    tick() {
        if (!this.state.timer) {
            this.state.elapsed = 0;
            return;
        }
        const start = deserializeDateTime(this.state.timer.date_time).ts;
        const elapsed = Math.floor((Date.now() + this.clockOffset - start) / 1000);
        // Clamp: a timer started "in the future" (a line hand-edited to
        // tomorrow) should read 0:00:00 rather than count down.
        const clamped = Math.max(0, elapsed);
        if (clamped !== this.state.elapsed) {
            this.state.elapsed = clamped;
        }
    }

    get formattedElapsed() {
        const total = this.state.elapsed;
        const hours = Math.floor(total / 3600);
        const minutes = Math.floor((total % 3600) / 60);
        const seconds = total % 60;
        const pad = (n) => String(n).padStart(2, "0");
        return `${hours}:${pad(minutes)}:${pad(seconds)}`;
    }

    get startedAt() {
        return deserializeDateTime(this.state.timer.date_time).toLocaleString(
            DateTime.TIME_SIMPLE
        );
    }

    /** What the timer is on, in one line, best label first. */
    get subtitle() {
        const timer = this.state.timer;
        return timer.origin_name || timer.task || timer.project || "";
    }

    async onStop() {
        if (this.state.stopping || !this.state.timer) {
            return;
        }
        this.state.stopping = true;
        try {
            await this.orm.call("account.analytic.line", "button_end_work", [
                [this.state.timer.id],
            ]);
        } finally {
            this.state.stopping = false;
        }
        this.dropdown.close();
        await this.load();
        this.notification.add(_t("Timer stopped."), { type: "success" });
        // Any form on screen computed its Start/Stop button before this, so
        // without a reload a repair order would keep offering to stop a timer
        // that is already stopped.
        await this.reloadCurrentView();
    }

    async onStart() {
        this.dropdown.close();
        await this.action.doAction(
            "project_timesheet_time_control.hr_timesheet_switch_action",
            {
                onClose: async () => {
                    await this.load();
                    await this.reloadCurrentView();
                },
            }
        );
    }

    async onOpenOrigin() {
        const timer = this.state.timer;
        if (!timer.origin_model) {
            return;
        }
        this.dropdown.close();
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: timer.origin_model,
            res_id: timer.origin_id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async reloadCurrentView() {
        await this.action.doAction({ type: "ir.actions.client", tag: "soft_reload" });
    }
}

export const systrayTimesheetTimer = {
    Component: TimesheetTimerSystray,
};

registry
    .category("systray")
    .add("hr_timesheet_time_control_systray.timer", systrayTimesheetTimer, {
        sequence: 99,
    });
