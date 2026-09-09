# Copyright 2026 Avunu LLC
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
"""Guards the generated per-company stylesheet.

The sharp edge here is that everything this module emits is a CUSTOM PROPERTY,
and Sass does not evaluate functions inside a custom property's value -- it
passes them through as plain CSS text. So `darken($c, 8%)` reaches the browser
verbatim, which is invalid and silently ignored: the hover state just stops
working, with nothing in any log. Every shade must therefore already be a
literal before it reaches the template.
"""
import base64
import re

from odoo.tests.common import TransactionCase, tagged

from ..models.res_company import CARBON, shade


@tagged("post_install", "-at_install")
class TestCarbonCompanyColor(TransactionCase):

    def _css(self, company):
        attachment = self.env["ir.attachment"].sudo().search(
            [("url", "=", company.scss_get_url()), ("company_id", "=", company.id)]
        )
        self.assertTrue(attachment, "web_company_color generated no attachment")
        return base64.b64decode(attachment.datas).decode("utf-8")

    @staticmethod
    def _declarations(css):
        """The stylesheet minus its comments.

        The comments explain, among other things, *why* no !important is
        needed -- so a naive substring search finds the word in the prose and
        fails a passing file.
        """
        return re.sub(r"/\*.*?\*/", "", css, flags=re.S)

    def setUp(self):
        super().setUp()
        self.company = self.env["res.company"].create({"name": "Carbon Test Co"})

    def test_shade_returns_literal_hex(self):
        self.assertEqual(shade("#ffffff", 0.0), "#ffffff")
        self.assertTrue(shade("#8a3ffc", 0.1).startswith("#"))
        self.assertEqual(len(shade("#8a3ffc", 0.1)), 7)
        # short form is accepted, since the field is a plain Char
        self.assertEqual(len(shade("#abc", 0.1)), 7)

    def test_shade_passes_through_nonsense(self):
        """A malformed colour must not raise during a res.company write."""
        for value in ("", "not-a-colour", None, "#12345"):
            self.assertEqual(shade(value, 0.1), value)

    def test_no_unevaluated_sass_functions(self):
        """The regression this module exists to avoid."""
        self.company.write({"color_button_bg": "#8a3ffc"})
        css = self._declarations(self._css(self.company))
        for fn in ("darken(", "lighten(", "mix(", "rgba($"):
            self.assertNotIn(
                fn,
                css,
                f"{fn} reached the stylesheet unevaluated. Sass does not resolve "
                f"functions inside custom property values -- compute the colour "
                f"in Python (see shade()) instead of emitting SCSS.",
            )

    def test_company_colour_drives_the_carbon_tokens(self):
        self.company.write({"color_button_bg": "#8a3ffc"})
        css = self._css(self.company)
        for token in ("--cds-interactive", "--cds-focus", "--cds-border-interactive",
                      "--cds-button-primary", "--btn-bg"):
            self.assertIn(f"{token}: #8a3ffc", css, f"{token} did not take the company colour")

    def test_unset_colours_fall_back_to_carbon(self):
        """A company that sets one colour must not get Odoo purple for the rest."""
        self.company.write({"color_button_bg": "#8a3ffc"})
        css = self._css(self.company)
        self.assertIn(CARBON["shell_bg"], css, "the shell lost its Carbon default")
        self.assertNotIn("#71639e", css, "web_company_color's Odoo purple leaked through")

    def test_no_important_needed(self):
        """We win by mechanism, not by escalation.

        Buttons go through Bootstrap's --btn-* custom properties and the rest
        through --cds-*, so nothing here should need !important. The stock
        web_company_color template is full of it; if any reappears, the
        template has been reverted rather than replaced.
        """
        self.company.write({"color_button_bg": "#8a3ffc"})
        self.assertNotIn("!important", self._declarations(self._css(self.company)))
