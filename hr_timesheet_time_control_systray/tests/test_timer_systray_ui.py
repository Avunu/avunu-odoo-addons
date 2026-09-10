# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, tagged
from odoo.tests.common import new_test_user


@tagged("post_install", "-at_install")
class TestTimerSystrayUi(HttpCase):
    """The half of this module the Python tests cannot reach.

    An import path that does not resolve, a QWeb template that does not parse
    or an SCSS variable that does not exist all leave the server perfectly
    happy and the navbar empty.
    """

    def test_timer_ticks_in_the_navbar_and_stops_from_there(self):
        company = self.env.company
        project = self.env["project.project"].create(
            {
                "name": "Shop Labor UI",
                "allow_timesheets": True,
                "company_id": company.id,
            }
        )
        # password_security rejects the login-as-password new_test_user
        # defaults to, and HttpCase has to actually log in.
        user = new_test_user(
            self.env,
            login="systray_tech_ui",
            password="Systray-Ui-Tech-1!",
            groups="base.group_user,"
            "hr_timesheet.group_hr_timesheet_user,"
            "project.group_project_user",
            company_id=company.id,
        )
        employee = self.env["hr.employee"].create(
            {"name": "Systray UI Tech", "user_id": user.id, "company_id": company.id}
        )
        self.env["account.analytic.line"].create(
            {
                "name": "Browser check",
                "project_id": project.id,
                "employee_id": employee.id,
                "unit_amount": 0,
                # Far enough back that the reading is unmistakably computed,
                # and on a round enough boundary that the tour's assertion
                # holds for the ten minutes after this line is written.
                "date_time": fields.Datetime.now() - timedelta(hours=1, minutes=30),
            }
        )

        self.start_tour("/odoo", "timer_systray_tour", login="systray_tech_ui")
