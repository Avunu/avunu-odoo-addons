# Copyright 2026 Avunu LLC
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
"""Guards the per-company brand colour configuration."""

from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

from ..models.res_company import (
    rgb_triple,
    CARBON_DARK,
    CARBON_LIGHT,
    CARBON_SHELL,
    blend,
    luma,
    parse_hex,
    readable_on,
    shift,
)


@tagged("post_install", "-at_install")
class TestCarbonBrand(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env["res.company"].create({"name": "Carbon Brand Co"})

    # -- colour helpers ------------------------------------------------------

    def test_parse_hex_accepts_both_forms(self):
        self.assertEqual(parse_hex("#ffffff"), (1.0, 1.0, 1.0))
        self.assertEqual(parse_hex("#fff"), (1.0, 1.0, 1.0))
        self.assertEqual(parse_hex("000000"), (0.0, 0.0, 0.0))

    def test_parse_hex_rejects_nonsense(self):
        """A malformed colour must not raise mid-write: the field is a Char."""
        for value in ("", "nope", None, "#12345", 42):
            self.assertIsNone(parse_hex(value))

    def test_shift_darkens_and_lightens(self):
        self.assertLess(shift("#808080", 0.2), "#808080")   # darker hex sorts lower
        self.assertGreater(shift("#808080", -0.2), "#808080")
        # and never runs off either end
        self.assertEqual(shift("#000000", 0.5), "#000000")
        self.assertEqual(shift("#ffffff", -0.5), "#ffffff")

    def test_shift_passes_through_nonsense(self):
        self.assertEqual(shift("nope", 0.1), "nope")

    def test_readable_on_picks_contrast(self):
        self.assertEqual(readable_on("#ffffff"), "#161616")
        self.assertEqual(readable_on("#161616"), "#f4f4f4")

    # -- palette resolution --------------------------------------------------

    def test_untouched_company_emits_nothing(self):
        """No configuration, no bytes -- the theme's own defaults stand."""
        self.assertFalse(self.company._carbon_is_customised())
        self.assertEqual(
            self.env["res.company"].with_company(self.company)._carbon_brand_style(), ""
        )

    def test_defaults_are_carbons_own(self):
        self.assertEqual(self.company._carbon_palette()["brand"], CARBON_LIGHT["brand"])
        self.assertEqual(
            self.company._carbon_palette(dark=True)["brand"], CARBON_DARK["brand"]
        )

    def test_dark_is_derived_from_light_when_unset(self):
        """The reason light and dark are separate fields at all.

        Carbon lightens its interactive tone on g100 because a mid-dark colour
        does not carry against near-black. A company that sets only a light
        brand must still get a legible dark one.
        """
        self.company.carbon_brand_light = "#009d9a"
        light = self.company._carbon_palette()["brand"]
        dark = self.company._carbon_palette(dark=True)["brand"]
        self.assertEqual(light, "#009d9a")
        self.assertNotEqual(dark, light)
        self.assertGreater(
            sum(parse_hex(dark)), sum(parse_hex(light)), "dark brand should be lighter"
        )

    def test_explicit_dark_wins_over_derivation(self):
        self.company.write(
            {"carbon_brand_light": "#009d9a", "carbon_brand_dark": "#ff00ff"}
        )
        self.assertEqual(self.company._carbon_palette(dark=True)["brand"], "#ff00ff")

    def test_on_brand_follows_contrast(self):
        self.company.carbon_brand_light = "#f1c21b"  # bright yellow
        self.assertEqual(self.company._carbon_palette()["on_brand"], "#161616")
        self.company.carbon_brand_light = "#002d9c"  # deep blue
        self.assertEqual(self.company._carbon_palette()["on_brand"], "#f4f4f4")

    def test_header_text_auto_contrasts(self):
        self.company.carbon_header_bg = "#ffffff"
        self.assertEqual(self.company._carbon_palette()["header_text"], "#161616")

    # -- emitted stylesheet --------------------------------------------------

    def _style(self):
        return str(
            self.env["res.company"].with_company(self.company)._carbon_brand_style()
        )

    def test_style_carries_the_brand_through_every_role(self):
        self.company.carbon_brand_light = "#009d9a"
        css = self._style()
        for token in (
            "--cds-interactive",
            "--cds-focus",
            "--cds-border-interactive",
            "--cds-button-primary",
            "--btn-bg",
        ):
            self.assertIn(f"{token}: #009d9a", css, f"{token} did not take the brand")

    def test_style_needs_no_important(self):
        """We win by mechanism, not escalation.

        Buttons go through Bootstrap's --btn-* custom properties and everything
        else through --cds-*, so the block is injected after the bundles and
        simply wins. If !important appears, something has stopped working.
        """
        self.company.carbon_brand_light = "#009d9a"
        body = self._style().split("*/")[-1]  # drop the explanatory comments
        self.assertNotIn("!important", body)

    def test_style_emits_only_literal_colours(self):
        """No unevaluated colour functions.

        These are custom property values, where a function would be passed
        through as plain text and silently ignored by the browser.
        """
        self.company.carbon_brand_light = "#009d9a"
        css = self._style()
        for fn in ("darken(", "lighten(", "mix("):
            self.assertNotIn(fn, css)

    # -- header ---------------------------------------------------------------

    def test_header_entries_follow_the_header_colour(self):
        """The bug this guards: a branded header with Carbon-shell entries.

        Odoo paints every navbar entry from $o-navbar-background, compiled to
        the near-black shell tone. Setting only .o_main_navbar left those
        entries as opaque dark blocks sitting on a coloured bar. They are
        re-pointed through Odoo's --NavBar-* custom properties instead.
        """
        self.company.carbon_header_bg = "#e8574c"
        css = self._style()
        for prop in (
            "--NavBar-entry-backgroundColor",
            "--NavBar-entry-backgroundColor--hover",
            "--NavBar-entry-backgroundColor--active",
            "--NavBar-entry-color",
            "--NavBar-brand-color",
        ):
            self.assertIn(prop, css, f"{prop} is not re-pointed at the header colour")
        self.assertIn("--NavBar-entry-backgroundColor: #e8574c", css)
        # and the theme's own header pieces follow through the shell aliases
        self.assertIn("--cds-shell-bg: #e8574c", css)

    def test_header_hover_moves_away_from_the_background(self):
        """Light headers must darken on hover, dark ones lighten.

        Carbon's shell lightens because it is near-black; applying that blindly
        to a light header would make "hover" mean "wash out".
        """
        self.company.carbon_header_bg = "#161616"
        dark_hover = self.company._carbon_palette()["header_hover"]
        self.assertGreater(luma(dark_hover), luma("#161616"))

        self.company.carbon_header_bg = "#f4f4f4"
        light_hover = self.company._carbon_palette()["header_hover"]
        self.assertLess(luma(light_hover), luma("#f4f4f4"))

    def test_header_defaults_stay_carbon(self):
        self.company.carbon_brand_light = "#009d9a"   # customised, header not
        palette = self.company._carbon_palette()
        self.assertEqual(palette["header_bg"], CARBON_SHELL["bg"])
        self.assertEqual(palette["header_hover"], CARBON_SHELL["hover"])

    def test_blend_moves_between_two_colours(self):
        self.assertEqual(blend("#000000", "#ffffff", 0.0), "#000000")
        self.assertEqual(blend("#000000", "#ffffff", 1.0), "#ffffff")
        self.assertEqual(blend("#000000", "#ffffff", 0.5), "#808080")
        self.assertEqual(blend("nope", "#ffffff", 0.5), "nope")

    def test_broken_palette_never_breaks_the_backend(self):
        """This renders into the webclient <head>.

        A raise here does not degrade the theme, it replaces the whole backend
        with a traceback -- which is what happened while developing it.
        """
        self.company.carbon_brand_light = "#009d9a"
        with patch.object(
            type(self.company), "_carbon_palette", side_effect=ValueError("boom")
        ):
            self.assertEqual(self._style(), "")

    # -- compiled Carbon blue that runtime tokens cannot reach ----------------

    def test_rgb_triple(self):
        """Bootstrap composes link colour from channels, not a hex string."""
        self.assertEqual(rgb_triple("#0f62fe"), "15, 98, 254")
        self.assertEqual(rgb_triple("#fff"), "255, 255, 255")
        self.assertIsNone(rgb_triple("nope"))

    def test_links_and_link_buttons_follow_the_brand(self):
        """Odoo compiles $o-main-link-color to a literal.

        The --cds-* tokens cannot reach an ordinary <a>, so every link and
        link-button stayed Carbon blue on a branded database until these were
        emitted. .btn-light is included because the theme maps it to Carbon's
        ghost button, which Odoo uses for the form save/discard buttons.
        """
        self.company.carbon_brand_light = "#cd4c4c"
        css = self._style()
        self.assertIn("--link-color-rgb: 205, 76, 76", css)
        self.assertIn("--link-hover-color-rgb", css)
        self.assertIn(".btn-link", css)
        self.assertIn(".btn-light", css)

    def test_open_dropdown_border_follows_the_brand(self):
        """dropdown.scss reads the button map directly, with no property behind it.

        `border-color: map-get($-value, 'active-border')` compiles to a
        Carbon-blue literal, so an open dropdown kept a blue rim regardless of
        the brand. It needs a real rule, not a token.
        """
        self.company.carbon_brand_light = "#cd4c4c"
        css = self._style()
        self.assertIn(".o-dropdown.btn-secondary.show", css)
        self.assertIn("border-color: #cd4c4c", css)

    def test_bootstrap_theme_colour_family_is_branded(self):
        """The highest-leverage override, and the least obvious.

        Odoo does NOT let Bootstrap generate .text-*/.bg-*: it builds them with
        o-print-color(), which emits `--color: RGBA(...); color: var(--color)
        !important`. So the utilities are re-pointed by setting the property
        Odoo's own !important rule reads -- the same trick the tag colours use --
        while the "subtle" family really is read off :root by Bootstrap.
        """
        self.company.carbon_brand_light = "#cd4c4c"
        css = self._style()
        self.assertIn("--primary: #cd4c4c", css)
        self.assertIn("--primary-rgb: 205, 76, 76", css)
        self.assertIn("--primary-bg-subtle", css)
        # utilities go through the custom property, not a plain declaration
        self.assertIn(".text-primary", css)
        self.assertIn("--color: rgba(205, 76, 76", css)
        self.assertIn(".text-action", css)

    def test_compiled_literals_get_real_rules(self):
        """Four places Odoo compiles a colour with no custom property behind it.

        Each needs an actual rule; a token cannot reach any of them.
        """
        self.company.carbon_brand_light = "#cd4c4c"
        css = self._style()
        for selector in (
            "--o-statusbar-border-active",              # status tracker ::before
            ".o_searchview:focus-within",               # search bar outline
            ".o-dropdown.btn-secondary.show",           # open dropdown rim
            ".dropdown-item.active",                    # selected-item checkmark
        ):
            self.assertIn(selector, css, f"{selector} is not branded")
