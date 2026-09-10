# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import json
from datetime import timedelta

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user

from ..models.account_analytic_line import TIMER_CHANGED


# post_install: creating a project touches fields owned by modules that load
# after this one, so the registry has to be complete before these run.
@tagged("post_install", "-at_install")
class TestTimerSystray(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.project = cls.env["project.project"].create(
            {
                "name": "Shop Labor",
                "allow_timesheets": True,
                "company_id": cls.company.id,
            }
        )
        cls.task = cls.env["project.task"].create(
            {"name": "Brake job", "project_id": cls.project.id}
        )
        cls.technician = cls._make_user("systray_tech_1", "Systray-Tech-1!")
        cls.employee = cls._make_employee(cls.technician, "Systray Tech 1")
        cls.other = cls._make_user("systray_tech_2", "Systray-Tech-2!")
        cls.other_employee = cls._make_employee(cls.other, "Systray Tech 2")
        # No timesheet group: this one should never be offered a timer.
        cls.bystander = new_test_user(
            cls.env,
            login="systray_bystander",
            password="Systray-Bystander-1!",
            groups="base.group_user",
            company_id=cls.company.id,
        )

    @classmethod
    def _make_user(cls, login, password):
        # password_security is installed and rejects the login-as-password that
        # new_test_user defaults to.
        return new_test_user(
            cls.env,
            login=login,
            password=password,
            groups="base.group_user,"
            "hr_timesheet.group_hr_timesheet_user,"
            "project.group_project_user",
            company_id=cls.company.id,
        )

    @classmethod
    def _make_employee(cls, user, name):
        return cls.env["hr.employee"].create(
            {"name": name, "user_id": user.id, "company_id": cls.company.id}
        )

    def _timer(self, employee=None, **vals):
        """A running timer: a timesheet line with no duration yet."""
        values = {
            "name": "Working",
            "project_id": self.project.id,
            "employee_id": (employee or self.employee).id,
            "unit_amount": 0,
            "date_time": fields.Datetime.now(),
        }
        values.update(vals)
        return self.env["account.analytic.line"].create(values)

    def _systray(self, user=None):
        """What the systray of that user's browser would be handed."""
        return (
            self.env["account.analytic.line"]
            .with_user(user or self.technician)
            .get_running_timer()
        )

    def _drain_notifications(self):
        """Flush queued bus messages and clear them.

        _bus_send only queues onto the cursor's precommit hook, so nothing is a
        record until that runs.
        """
        self.env.cr.precommit.run()
        self.env["bus.bus"].search([]).unlink()

    def _notified_partners(self):
        """Partners told about a timer change since the last drain."""
        self.env.cr.precommit.run()
        partners = self.env["res.partner"]
        for message in self.env["bus.bus"].search([]):
            if json.loads(message.message)["type"] != TIMER_CHANGED:
                continue
            # channel is json_dump((dbname, model, id)) for a record channel.
            channel = json.loads(message.channel)
            if isinstance(channel, list) and channel[1] == "res.partner":
                partners |= partners.browse(channel[2])
        return partners

    # -- payload ----------------------------------------------------------

    def test_hidden_from_users_without_the_timesheet_group(self):
        data = self._systray(self.bystander)
        self.assertFalse(data["enabled"])
        # Nothing else is even computed for them.
        self.assertNotIn("timer", data)

    def test_reports_no_timer_when_none_is_running(self):
        data = self._systray()
        self.assertTrue(data["enabled"])
        self.assertFalse(data["timer"])
        self.assertEqual(data["running_count"], 0)

    def test_reports_the_running_timer(self):
        line = self._timer(name="Fitting pads")
        data = self._systray()
        self.assertEqual(data["running_count"], 1)
        self.assertEqual(data["timer"]["id"], line.id)
        self.assertEqual(data["timer"]["name"], "Fitting pads")
        self.assertEqual(data["timer"]["project"], self.project.display_name)
        self.assertEqual(
            fields.Datetime.from_string(data["timer"]["date_time"]), line.date_time
        )

    def test_a_stopped_line_is_not_a_running_timer(self):
        self._timer(unit_amount=1.5)
        self.assertFalse(self._systray()["timer"])

    def test_server_time_lets_the_client_correct_its_clock(self):
        stamped = fields.Datetime.from_string(self._systray()["server_time"])
        self.assertLess(abs(stamped - fields.Datetime.now()), timedelta(seconds=30))

    def test_origin_is_the_task_when_there_is_one(self):
        self._timer(task_id=self.task.id)
        timer = self._systray()["timer"]
        self.assertEqual(timer["origin_model"], "project.task")
        self.assertEqual(timer["origin_id"], self.task.id)
        self.assertEqual(timer["task"], self.task.display_name)

    def test_origin_falls_back_to_the_project(self):
        self._timer()
        timer = self._systray()["timer"]
        self.assertEqual(timer["origin_model"], "project.project")
        self.assertEqual(timer["origin_id"], self.project.id)

    def test_every_timer_capable_model_is_discovered(self):
        """The back-link of each mixin model must be an origin candidate.

        This is what saves a glue module per vertical: install
        repair_timesheet_time_control and repair_order_id turns up here on its
        own, because the mixin already declares it.
        """
        candidates = self.env["account.analytic.line"]._timer_systray_origin_fields()
        declared = set()
        for model_name in self.env["ir.model"].search([]).mapped("model"):
            model = self.env[model_name]
            # The mixin is abstract and its own implementation raises.
            if model._abstract:
                continue
            relation = getattr(model, "_relation_with_timesheet_line", None)
            if relation:
                declared.add(relation())
        self.assertTrue(declared, "No timer-capable model found at all")
        self.assertFalse(declared - set(candidates))

    def test_project_and_task_are_the_last_resort(self):
        """A more specific back-link must beat them, or Open is useless."""
        candidates = self.env["account.analytic.line"]._timer_systray_origin_fields()
        self.assertEqual(candidates[-2:], ["task_id", "project_id"])

    def test_only_the_owner_sees_their_timer(self):
        self._timer()
        self.assertTrue(self._systray()["timer"])
        self.assertFalse(self._systray(self.other)["timer"])

    def test_most_recent_timer_wins_and_the_count_is_reported(self):
        """Two running timers must inform, not break.

        The switch wizard refuses to start work while more than one is
        running, so the systray has to be able to say why.
        """
        old = self._timer(date_time=fields.Datetime.now() - timedelta(hours=2))
        new = self._timer()
        data = self._systray()
        self.assertEqual(data["running_count"], 2)
        self.assertEqual(data["timer"]["id"], new.id)
        self.assertNotEqual(data["timer"]["id"], old.id)

    # -- bus notifications -------------------------------------------------

    def test_starting_a_timer_notifies_its_owner(self):
        self._drain_notifications()
        self._timer()
        self.assertIn(self.technician.partner_id, self._notified_partners())

    def test_stopping_a_timer_notifies_its_owner(self):
        line = self._timer(date_time=fields.Datetime.now() - timedelta(hours=1))
        self._drain_notifications()
        line.button_end_work()
        self.assertIn(self.technician.partner_id, self._notified_partners())

    def test_deleting_a_timer_notifies_its_owner(self):
        line = self._timer()
        self._drain_notifications()
        line.unlink()
        self.assertIn(self.technician.partner_id, self._notified_partners())

    def test_an_unrelated_write_notifies_nobody(self):
        line = self._timer()
        self._drain_notifications()
        line.name = "Renamed"
        self.assertFalse(self._notified_partners())

    def test_reassigning_a_timer_notifies_both_users(self):
        line = self._timer()
        self._drain_notifications()
        line.employee_id = self.other_employee
        notified = self._notified_partners()
        self.assertIn(self.technician.partner_id, notified)
        self.assertIn(self.other.partner_id, notified)

    def test_a_stopped_line_being_edited_notifies_nobody(self):
        """Correcting last week's hours must not ping anyone's systray."""
        line = self._timer(unit_amount=2)
        self._drain_notifications()
        line.unit_amount = 3
        self.assertFalse(self._notified_partners())
