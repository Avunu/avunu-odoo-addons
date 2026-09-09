# Copyright 2026 Avunu LLC
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
"""Per-company brand colours, expressed as Carbon design tokens.

A brand colour is set once and reaches everything the theme draws from the
Carbon interactive family: primary buttons, links, focus rings, selected rows,
the notebook underline, the search-panel rule, the statusbar current step. It
is not a header tint -- the header is a separate setting precisely because the
two are different decisions.

Light and dark are separate colours on purpose. Carbon does not reuse one
interactive tone across themes: its own is Blue 60 (#0f62fe) on g10 and the
lighter Blue 50 (#4589ff) on g100, because a mid-dark blue that reads well on
#f4f4f4 does not carry against #161616. A single brand colour applied to both
would be legible in one theme and muddy in the other, so a dark variant is
either given or derived by lightening.

Delivery is a small <style> block injected into the webclient head after the
asset bundles, rather than a generated stylesheet:

* every value is a CSS custom property, so no SCSS compilation is involved and
  none of libsass's constraints apply;
* the head is rendered per request anyway, and the block is well under 2 KB;
* the theme is chosen server-side per request, so the correct variant can be
  emitted directly instead of shipping both and letting the cascade decide.
"""

from colorsys import hls_to_rgb, rgb_to_hls

from markupsafe import Markup

from odoo import api, fields, models
from odoo.http import request

# Carbon's own values, mirrored from
# static/src/scss/generated/_carbon_tokens{,_dark}.scss. They are the fallback
# for every unset field, so a company that sets one colour still gets a
# coherent Carbon palette rather than a half-branded one.
CARBON_LIGHT = {
    "brand": "#0f62fe",  # Blue 60  -- interactive / button-primary
    "brand_hover": "#0050e6",
    "brand_active": "#002d9c",
    "link": "#0f62fe",
    "link_hover": "#0043ce",
    "on_brand": "#ffffff",
}
CARBON_DARK = {
    "brand": "#4589ff",  # Blue 50  -- Carbon lightens interactive on g100
    "brand_hover": "#5e94ff",
    "brand_active": "#95baff",
    "link": "#78a9ff",  # Blue 40
    "link_hover": "#a6c8ff",
    "on_brand": "#ffffff",
}
CARBON_SHELL = {
    "bg": "#161616",  # the UI Shell header is g100 in every Carbon theme
    "border": "#393939",
    "text": "#f4f4f4",
}


def parse_hex(value):
    """``#abc`` / ``#aabbcc`` -> (r, g, b) floats, or None if not a hex colour.

    These arrive from a ``widget="color"`` field and are normally well formed,
    but the field is a plain Char and nothing stops a value being written
    another way. A malformed colour has to degrade to "leave it alone" rather
    than raise in the middle of a res.company write.
    """
    if not isinstance(value, str):
        return None
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(c * 2 for c in text)
    if len(text) != 6:
        return None
    try:
        return tuple(int(text[i : i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return None


def shift(value, amount):
    """Shift a hex colour's lightness. Positive darkens, negative lightens.

    Computed in Python rather than emitted as ``darken()`` for the CSS to
    resolve. Everything here is a CSS custom property, and Sass does not
    evaluate functions inside a custom property's value -- it passes them
    through as plain text -- so a colour has to be literal before it is
    written. (Nothing compiles this string today, but the constraint is one
    step away and the failure is silent: an unevaluated function is simply
    ignored by the browser.)
    """
    rgb = parse_hex(value)
    if rgb is None:
        return value
    hue, lightness, saturation = rgb_to_hls(*rgb)
    lightness = min(1.0, max(0.0, lightness - amount))
    red, green, blue = hls_to_rgb(hue, lightness, saturation)
    return "#%02x%02x%02x" % (int(red * 255), int(green * 255), int(blue * 255))


def readable_on(background):
    """Black or white, whichever reads better on `background`.

    Rec. 709 luma, the same measure web_company_color uses to pick navbar text.
    """
    rgb = parse_hex(background)
    if rgb is None:
        return CARBON_SHELL["text"]
    luma = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    return "#161616" if luma > 0.5 else "#f4f4f4"


class ResCompany(models.Model):
    _inherit = "res.company"

    carbon_brand_light = fields.Char(
        string="Brand colour (light)",
        help="Primary colour for the light theme. Used for primary buttons, "
        "links, focus rings, selected rows, active tabs and the status bar — "
        "not just the header. Leave empty for Carbon Blue 60 (#0f62fe).",
    )
    carbon_brand_dark = fields.Char(
        string="Brand colour (dark)",
        help="Primary colour for the dark theme. Carbon uses a lighter tone "
        "here than in light, because a mid-dark colour does not carry against "
        "a near-black background. Leave empty to lighten the light brand "
        "colour automatically, or Carbon Blue 50 (#4589ff) if that is unset too.",
    )
    carbon_header_bg = fields.Char(
        string="Header background",
        help="Background of the top bar. Carbon keeps its header near-black in "
        "both themes. Leave empty for #161616.",
    )
    carbon_header_text = fields.Char(
        string="Header text",
        help="Leave empty to pick black or white automatically, whichever "
        "reads better on the header background.",
    )

    def _carbon_is_dark(self):
        """Whether this request is being served the dark bundle.

        Odoo switches theme by serving a different bundle, keyed on the
        color_scheme cookie -- there is no class or data attribute to read.
        Odoo 19 exposes ir.http.color_scheme(); 18 only has the cookie.
        """
        color_scheme = None
        get_scheme = getattr(self.env["ir.http"], "color_scheme", None)
        if get_scheme:
            try:
                color_scheme = get_scheme()
            except Exception:  # pragma: no cover - defensive across versions
                color_scheme = None
        if color_scheme is None and request:
            color_scheme = request.httprequest.cookies.get("color_scheme")
        return color_scheme == "dark"

    def _carbon_palette(self, dark=False):
        """Resolve the company's fields into a full Carbon interactive palette."""
        self.ensure_one()
        base = CARBON_DARK if dark else CARBON_LIGHT

        if dark:
            # An explicit dark brand wins; otherwise lighten the light one, which
            # is what Carbon does between g10 and g100. Only if neither is set do
            # we fall back to Carbon's own dark interactive tone.
            brand = self.carbon_brand_dark or (
                shift(self.carbon_brand_light, -0.12)
                if self.carbon_brand_light
                else base["brand"]
            )
        else:
            brand = self.carbon_brand_light or base["brand"]

        is_carbon_default = brand == base["brand"]
        # Carbon's own hover/active steps are hand-tuned, so they are used
        # verbatim when the colour is unchanged; a custom brand gets the same
        # relative treatment. Dark themes brighten on hover instead of darkening.
        direction = -1 if dark else 1
        header_bg = self.carbon_header_bg or CARBON_SHELL["bg"]

        return {
            "brand": brand,
            "brand_hover": base["brand_hover"] if is_carbon_default else shift(brand, 0.06 * direction),
            "brand_active": base["brand_active"] if is_carbon_default else shift(brand, 0.16 * direction),
            "on_brand": base["on_brand"] if is_carbon_default else readable_on(brand),
            "link": brand,
            "link_hover": base["link_hover"] if is_carbon_default else shift(brand, 0.10 * direction),
            "header_bg": header_bg,
            "header_border": shift(header_bg, -0.08) if header_bg != CARBON_SHELL["bg"] else CARBON_SHELL["border"],
            "header_text": self.carbon_header_text or readable_on(header_bg),
        }

    def _carbon_is_customised(self):
        self.ensure_one()
        return any(
            (
                self.carbon_brand_light,
                self.carbon_brand_dark,
                self.carbon_header_bg,
                self.carbon_header_text,
            )
        )

    @api.model
    def _carbon_brand_style(self):
        """The <style> body injected into the webclient head, or empty.

        Emitted only when a company has actually set something, so an untouched
        database ships no extra bytes and the theme's own defaults stand.
        """
        company = self.env.company
        if not company or not company._carbon_is_customised():
            return Markup("")
        palette = company._carbon_palette(dark=company._carbon_is_dark())
        return Markup(
            """
/* web_theme_carbon: %(name)s brand colours, as Carbon tokens. */
:root {
    --cds-interactive: %(brand)s;
    --cds-border-interactive: %(brand)s;
    --cds-focus: %(brand)s;
    --cds-background-brand: %(brand)s;
    --cds-link-primary: %(link)s;
    --cds-link-primary-hover: %(link_hover)s;
    --cds-button-primary: %(brand)s;
    --cds-button-primary-hover: %(brand_hover)s;
    --cds-button-primary-active: %(brand_active)s;
    --cds-button-tertiary: %(brand)s;
}
/* Odoo compiles .btn-* to literals from $o-btns-bs-override, so the tokens
   above cannot reach them. Bootstrap's button-variant() writes --btn-* and
   .btn reads it back (Odoo sets $variable-prefix to ''), so setting those
   properties is enough -- no !important, and no dependence on load order. */
.btn-primary {
    --btn-color: %(on_brand)s;
    --btn-bg: %(brand)s;
    --btn-border-color: %(brand)s;
    --btn-hover-color: %(on_brand)s;
    --btn-hover-bg: %(brand_hover)s;
    --btn-hover-border-color: %(brand_hover)s;
    --btn-active-color: %(on_brand)s;
    --btn-active-bg: %(brand_active)s;
    --btn-active-border-color: %(brand_active)s;
    --btn-disabled-color: %(on_brand)s;
    --btn-disabled-bg: %(brand)s;
    --btn-disabled-border-color: %(brand)s;
}
.btn-outline-primary {
    --btn-color: %(brand)s;
    --btn-border-color: %(brand)s;
    --btn-hover-color: %(on_brand)s;
    --btn-hover-bg: %(brand_hover)s;
    --btn-hover-border-color: %(brand_hover)s;
    --btn-active-color: %(on_brand)s;
    --btn-active-bg: %(brand_active)s;
    --btn-active-border-color: %(brand_active)s;
}
/* The header is the one surface the theme compiles from SCSS variables
   ($o-navbar-*), which no custom property can reach. */
.o_main_navbar {
    background-color: %(header_bg)s;
    border-bottom: 1px solid %(header_border)s;
    color: %(header_text)s;
}
"""
            % dict(palette, name=company.name)
        )
