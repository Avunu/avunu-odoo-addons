# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
{
    "name": "Timesheet Time Control Systray",
    "summary": "Show the running timesheet timer, ticking, in the systray, "
    "with a stop button that works from any screen",
    "version": "18.0.1.0.0",
    "category": "Human Resources/Timesheets",
    "author": "Avunu LLC",
    "website": "https://avu.nu",
    "license": "AGPL-3",
    # project_timesheet_time_control owns the notion of a running timer (an
    # analytic line with no duration yet); bus carries the change notification
    # that keeps a second tab, or a second device, honest.
    "depends": [
        "project_timesheet_time_control",
        "bus",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_timesheet_time_control_systray/static/src/timer_systray/timer_systray.js",
            "hr_timesheet_time_control_systray/static/src/timer_systray/timer_systray.xml",
            "hr_timesheet_time_control_systray/static/src/timer_systray/timer_systray.scss",
        ],
        "web.assets_tests": [
            "hr_timesheet_time_control_systray/static/tests/tours/**/*",
        ],
    },
    "installable": True,
}
