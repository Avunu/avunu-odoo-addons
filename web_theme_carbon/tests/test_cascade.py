# Copyright 2026 Avunu LLC
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
"""Asserts our declarations actually win in the compiled asset bundles.

This guards a failure mode that is completely silent: Odoo marks a declaration
``!important`` -- often from inside a mixin, e.g. ``o-print-color()`` expands to

    --background-color: RGBA(...);
    background-color: var(--background-color) !important;

-- and our rule then loses no matter how late it loads. The bundle still
compiles, nothing is logged, and the component just quietly keeps stock Odoo
styling. That is exactly what happened to the tag colours during development.

It is deliberately tested here rather than in tools/audit.mjs: deciding this
from the SCSS sources means guessing across nested selectors and mixins, and
every static version of the check produced false alarms that the compiled
bundle disproved. Here the answer is unambiguous.
"""
import re

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCarbonCascade(TransactionCase):

    # (bundle, class, property, marker that identifies OUR value)
    EXPECTATIONS = [
        ("web.assets_backend", "o_kanban_record", "background-color", "--cds-"),
        ("web.assets_backend", "o_grid_apps_menu", "background-color", "--cds-"),
        ("web.assets_backend", "o_tag_color_1", "--background-color", "tag-background-"),
        ("web.assets_backend", "o_last_breadcrumb_item", "font-size", "1.25rem"),
        ("web.assets_backend", "o_notification", "background-color", "--cds-"),
        ("web.assets_web_dark", "o_kanban_record", "background-color", "--cds-"),
    ]

    def _bundle_css(self, name):
        attachment = self.env["ir.qweb"]._get_asset_bundle(name, css=True, js=False).css()
        raw = attachment.raw if hasattr(attachment, "raw") else attachment[0].raw
        return raw.decode("utf-8", "replace")

    @staticmethod
    def _is_subject(selector, cls):
        """True when `cls` is the SUBJECT of the selector, not an ancestor.

        Matching on "the class appears anywhere in the selector" is wrong and
        produced a false alarm during development: web_dark_mode styles
        `.o_kanban_record:not(...) .o_attachment_image > img` with a white
        background, which is a nested image, not the card. Only the last
        compound selector -- what the rule actually paints -- counts.
        """
        for part in selector.split(","):
            subject = re.split(r"[\s>+~]+", part.strip())[-1]
            if cls in subject:
                return True
        return False

    def _winner(self, css, cls, prop):
        """The declaration a browser would actually apply.

        Later wins, unless an earlier one is !important -- which is the whole
        point of the test.
        """
        found = []
        for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            if not self._is_subject(selector, cls):
                continue
            for match in re.finditer(
                r"(?:^|;)\s*%s\s*:\s*([^;]+)" % re.escape(prop), body
            ):
                found.append(match.group(1).strip())
        if not found:
            return None
        important = [v for v in found if "!important" in v]
        return important[-1] if important else found[-1]

    def test_our_declarations_win(self):
        cache = {}
        for bundle, cls, prop, marker in self.EXPECTATIONS:
            css = cache.setdefault(bundle, self._bundle_css(bundle))
            winner = self._winner(css, cls, prop)
            self.assertIsNotNone(
                winner, f"{bundle}: no `{prop}` declaration found for .{cls}"
            )
            self.assertIn(
                marker,
                winner,
                f"{bundle}: .{cls} {{ {prop} }} resolves to {winner!r}, which is not "
                f"ours (expected to contain {marker!r}). Odoo most likely marks this "
                f"!important; set the custom property its rule reads instead of "
                f"escalating.",
            )

    def test_dark_bundle_overrides_light_tokens(self):
        """g100 must be declared after g10, or dark mode silently stays light."""
        css = self._bundle_css("web.assets_web_dark")
        values = re.findall(r"--cds-background:\s*([^;]+);", css)
        self.assertTrue(values, "no --cds-background in the dark bundle")
        self.assertEqual(
            values[-1].strip(),
            "#161616",
            "the last --cds-background in assets_web_dark is not g100's; the dark "
            "token file is no longer appended after the light one",
        )
