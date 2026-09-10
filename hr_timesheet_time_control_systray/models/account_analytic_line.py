# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models

# Notification type the systray subscribes to. The payload is deliberately
# empty: every client refetches its own timer with its own access rights, so
# nothing about one user's work travels down another user's channel.
TIMER_CHANGED = "hr_timesheet_time_control_systray.timer_changed"

# Writes that can change whether a line is a running timer, or whose it is.
# Anything else -- a description edit, an invoicing flag -- leaves every
# systray showing exactly what it already shows, and must not cost a
# notification.
TIMER_TRIGGER_FIELDS = frozenset(
    {"date_time", "unit_amount", "user_id", "employee_id", "project_id"}
)


class AccountAnalyticLine(models.Model):
    _inherit = "account.analytic.line"

    @api.model
    def _timer_systray_enabled(self):
        """Whether the current user gets a systray timer at all."""
        return self.env.user.has_group("hr_timesheet.group_hr_timesheet_user")

    @api.model
    def _timer_systray_origin_fields(self):
        """Back-links to records that can drive a timer, most specific first.

        Every model that drives a timer through the OCA mixin already declares
        which field on this line points back at it, via
        ``_relation_with_timesheet_line``. Reading those declarations means
        repair orders and maintenance requests are picked up without this
        module knowing either exists, and without a glue module per vertical.

        Project and task come last because every timesheet line has them; a
        repair order is the more useful thing to be sent back to.
        """
        generic = ["task_id", "project_id"]
        discovered = []
        for name, field in self._fields.items():
            if field.type != "many2one" or field.comodel_name not in self.env:
                continue
            relation = getattr(
                self.env[field.comodel_name], "_relation_with_timesheet_line", None
            )
            # Only the mixin defines that method, and a model that defines it
            # names exactly one field here -- so this both identifies the
            # timer-capable models and confirms the back-link is this field.
            if relation and relation() == name and name not in generic:
                discovered.append(name)
        return discovered + generic

    def _timer_systray_origin(self):
        """The record this timer is *about*, for the systray's open button."""
        self.ensure_one()
        for name in self._timer_systray_origin_fields():
            record = self[name] if name in self._fields else False
            if record:
                return record
        return False

    def _timer_systray_data(self):
        """Serialise one running line for the systray."""
        self.ensure_one()
        origin = self._timer_systray_origin()
        return {
            "id": self.id,
            "name": self.name or "",
            # Serialised UTC. The client works out elapsed time itself, once a
            # second, without asking the server again.
            "date_time": fields.Datetime.to_string(self.date_time),
            "project": self.project_id.display_name or "",
            "task": self.task_id.display_name or "",
            "origin_model": origin._name if origin else False,
            "origin_id": origin.id if origin else False,
            "origin_name": origin.display_name if origin else "",
        }

    @api.model
    def get_running_timer(self):
        """Everything the systray needs, in one round trip."""
        if not self._timer_systray_enabled():
            return {"enabled": False}
        running = self.search(self._running_domain(), order="date_time desc")
        return {
            "enabled": True,
            # The one thing here that cannot be trusted is the browser clock:
            # a tablet whose time has drifted would otherwise show a timer that
            # is minutes off, or negative. The client diffs this against its
            # own clock and applies the difference. Network latency biases it
            # by a few dozen milliseconds, which does not matter for a counter
            # displayed to the second.
            "server_time": fields.Datetime.to_string(fields.Datetime.now()),
            # Only ever one timer is shown, but say how many there are: the
            # switch wizard refuses to run with more than one, so a technician
            # who has somehow ended up with two needs telling rather than a
            # dead Start button.
            "timer": running[:1]._timer_systray_data() if running else False,
            "running_count": len(running),
        }

    @api.model
    def _timer_systray_notify(self, users):
        """Ping these users' browsers so their systray refetches.

        Queued on the cursor's precommit hook by ``_bus_send``, so a rolled
        back transaction notifies nobody.
        """
        partners = users.sudo().partner_id
        if partners:
            partners._bus_send(TIMER_CHANGED, {})

    def _timer_systray_relevant(self):
        """Lines that could plausibly be somebody's running timer.

        Deliberately looser than ``_running_domain``: over-notifying costs one
        cheap refetch that returns the same answer, while under-notifying
        leaves a stale timer on screen, which is the whole bug this module
        exists to avoid.
        """
        return self.filtered(lambda line: line.date_time and not line.unit_amount)

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        self._timer_systray_notify(lines._timer_systray_relevant().user_id)
        return lines

    def write(self, vals):
        if not TIMER_TRIGGER_FIELDS.intersection(vals):
            return super().write(vals)
        # Owners on both sides of the write: stopping a timer has to notify the
        # user whose line stops qualifying, and reassigning one has to clear it
        # from the previous owner's systray as well as light it on the new
        # owner's.
        users = self._timer_systray_relevant().user_id
        result = super().write(vals)
        self._timer_systray_notify(users | self._timer_systray_relevant().user_id)
        return result

    def unlink(self):
        users = self._timer_systray_relevant().user_id
        result = super().unlink()
        self._timer_systray_notify(users)
        return result
