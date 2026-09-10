# Timesheet Time Control Systray

Puts the running timesheet timer in the systray, counting up, on every screen.

`project_timesheet_time_control` (OCA) can start and stop a timer from a
project, a task or -- via `repair_timesheet_time_control` -- a repair order.
What it cannot do is tell you a timer is running while you are looking at
anything else: the running line is an `account.analytic.line` whose duration
stays `0:00` until it is stopped, so the only way to find it is to navigate to
*Timesheets > All Timesheets* and spot the row with a stop button. Odoo's own
ticking timer lives in Enterprise (`timer` + `timesheet_grid`) and is not an
option on Community.

This module adds:

- A navbar clock that shows `H:MM:SS` since the running timer started.
- A dropdown with the description, what the timer is on, when it started, and
  buttons to open that record or stop the timer.
- A *Start work* button when nothing is running, opening the same
  `hr.timesheet.switch` wizard the record buttons use.

It binds to `account.analytic.line`, not to any one origin model, so it covers
project tasks, maintenance requests and repair orders alike.

## How it stays accurate

- **Elapsed time is computed in the browser**, once a second, from the start
  time -- no polling.
- **The browser clock is not trusted.** `get_running_timer` returns the server
  clock alongside the timer, and the client applies the difference. A shop
  floor tablet whose clock has drifted still shows the right elapsed time.
- **Changes arrive over the bus.** Creating, stopping, reassigning or deleting
  a running line pings its owners' browsers, so a timer started in one tab
  appears in another, and on another device. The payload is empty by design:
  each client refetches its own timer under its own access rights.
- **Focus is a fallback.** Returning to the tab refetches, so a session whose
  websocket never came up still self-corrects.
- **Stopping refreshes the screen.** `show_time_control` is a compute with no
  live dependency on the systray, so stopping from the navbar triggers a
  `soft_reload`; an open repair order flips back to *Start Timer* rather than
  offering to stop a timer that is already stopped.

## Where *Open* goes

Nowhere is hardcoded, and no glue module is needed per vertical. Every model
that drives a timer through the OCA mixin already declares which field on
`account.analytic.line` points back at it, via
`_relation_with_timesheet_line()` -- `task_id` for tasks, `repair_order_id`
for repair orders, `maintenance_request_id` for maintenance requests. The
systray reads those declarations at runtime and prefers the most specific
back-link the running line has, falling back to task and then project.

So a repair order timer opens the repair order, with
`repair_timesheet_time_control` needing no change and this module needing no
dependency on `repair`. Override `_timer_systray_origin_fields()` to reorder,
or `_timer_systray_origin()` to decide differently.

## More than one running timer

`hr.timesheet.switch` raises rather than guess which of several timers to
stop. The systray shows the most recently started one and warns how many are
running, so the state is visible instead of just breaking the Start button.
