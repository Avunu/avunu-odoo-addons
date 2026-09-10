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

import logging
from colorsys import hls_to_rgb, rgb_to_hls

from markupsafe import Markup

from odoo import api, fields, models
from odoo.http import request

_logger = logging.getLogger(__name__)

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
    "text_secondary": "#c6c6c6",
    "hover": "#353535",
    "active": "#393939",
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


def blend(colour, towards, amount):
    """Mix `colour` `amount` of the way towards `towards`. Both hex, result hex."""
    a, b = parse_hex(colour), parse_hex(towards)
    if a is None or b is None:
        return colour
    mixed = [a[i] + (b[i] - a[i]) * amount for i in range(3)]
    return "#%02x%02x%02x" % tuple(int(round(c * 255)) for c in mixed)


def rgb_triple(colour):
    """`#0f62fe` -> `15, 98, 254`, for the `*-rgb` custom properties.

    Bootstrap composes link colour as
    `rgba(var(--link-color-rgb), var(--link-opacity, 1))`, so branding links
    means supplying the channels, not a hex string.
    """
    rgb = parse_hex(colour)
    if rgb is None:
        return None
    return ", ".join(str(int(round(c * 255))) for c in rgb)


def luma(colour):
    """Rec. 709 relative luminance, 0..1. Returns None for a bad colour."""
    rgb = parse_hex(colour)
    if rgb is None:
        return None
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def readable_on(background):
    """Black or white, whichever reads better on `background`.

    Rec. 709 luma, the same measure web_company_color uses to pick navbar text.
    """
    value = luma(background)
    if value is None:
        return CARBON_SHELL["text"]
    return "#161616" if value > 0.5 else "#f4f4f4"


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
        header_text = self.carbon_header_text or readable_on(header_bg)
        is_default_shell = header_bg == CARBON_SHELL["bg"]

        return {
            "brand": brand,
            "brand_hover": base["brand_hover"] if is_carbon_default else shift(brand, 0.06 * direction),
            "brand_active": base["brand_active"] if is_carbon_default else shift(brand, 0.16 * direction),
            "on_brand": base["on_brand"] if is_carbon_default else readable_on(brand),
            "link": brand,
            "link_hover": base["link_hover"] if is_carbon_default else shift(brand, 0.10 * direction),
            "brand_rgb": rgb_triple(brand) or "15, 98, 254",
            # Bootstrap 5.3's "subtle" family, which it tints from $primary at
            # compile time and re-exposes on :root.
            "brand_bg_subtle": blend(brand, "#ffffff", 0.8),
            "brand_border_subtle": blend(brand, "#ffffff", 0.6),
            "brand_text_emphasis": shift(brand, 0.2),
            "link_rgb": rgb_triple(brand) or "15, 98, 254",
            "link_hover_rgb": (
                rgb_triple(base["link_hover"] if is_carbon_default else shift(brand, 0.10 * direction))
                or "0, 67, 206"
            ),
            "header_bg": header_bg,
            "header_border": shift(header_bg, -0.08) if header_bg != CARBON_SHELL["bg"] else CARBON_SHELL["border"],
            "header_text": header_text,
            # Carbon's shell lightens on hover because it is near-black. A
            # mid-tone or light header has to go the other way, or "hover"
            # would mean "wash out".
            "header_hover": (
                CARBON_SHELL["hover"] if is_default_shell
                else shift(header_bg, -0.06 if (luma(header_bg) or 0) < 0.5 else 0.06)
            ),
            "header_active": (
                CARBON_SHELL["active"] if is_default_shell
                else shift(header_bg, -0.10 if (luma(header_bg) or 0) < 0.5 else 0.10)
            ),
            # The de-emphasised label colour. Carbon uses gray-30 on its own
            # shell; on a branded header the equivalent is the header's text
            # pulled a little way back towards the header itself.
            "header_text_secondary": (
                CARBON_SHELL["text_secondary"] if is_default_shell
                else blend(header_text, header_bg, 0.25)
            ),
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
        try:
            palette = company._carbon_palette(dark=company._carbon_is_dark())
        except Exception:  # pragma: no cover - defensive
            # This renders into the webclient <head>. A raise here does not
            # degrade the theme, it takes the entire backend down with a
            # traceback instead of a page -- which is exactly what happened
            # while developing this method. A styling asset must never be able
            # to do that, so a broken palette falls back to no branding at all.
            _logger.exception("web_theme_carbon: could not build the brand palette")
            return Markup("")
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
/* Bootstrap's theme colour. This is the single highest-leverage override
   here: Odoo compiles $primary (= $o-brand-primary) to a literal, and
   Bootstrap re-exposes it on :root, so EVERY .text-primary, .bg-primary,
   .border-primary and every `rgba(var(--primary-rgb), ...)` tint reads from
   these two. The company switcher's checked icon and its selected-row tint
   are both this, and so is most stray blue elsewhere. */
:root {
    --primary: %(brand)s;
    --primary-rgb: %(brand_rgb)s;
    /* Bootstrap 5.3's subtle family. .bg-primary-subtle reads these straight
       off :root, and it is what tints the company switcher's selected row. */
    --primary-bg-subtle: %(brand_bg_subtle)s;
    --primary-border-subtle: %(brand_border_subtle)s;
    --primary-text-emphasis: %(brand_text_emphasis)s;

    /* Links. Odoo compiles $o-main-link-color into a literal, so the tokens
       above cannot reach an ordinary <a>. Bootstrap composes an anchor from
       channels -- `rgba(var(--link-color-rgb), var(--link-opacity, 1))` --
       but other rules read the plain --link-color, so both forms are needed. */
    --link-color: %(link)s;
    --link-color-rgb: %(link_rgb)s;
    --link-hover-color-rgb: %(link_hover_rgb)s;
}

/* Odoo does NOT use Bootstrap's --primary-rgb for its utilities: it generates
   .text-* and .bg-* itself through o-print-color(), which emits
       --color: RGBA(...);  color: var(--color) !important;
   So the utilities have to be re-pointed the same way the tag colours are --
   by setting the custom property Odoo's own !important rule reads, rather than
   trying to outrank it. The company switcher's checked icon (.text-primary)
   and its selected-row tint (.bg-primary at low opacity) are both this. */
.text-primary {
    --color: rgba(%(brand_rgb)s, var(--text-opacity, 1));
}

.bg-primary {
    --background-color: rgba(%(brand_rgb)s, var(--bg-opacity, 1));
}

.border-primary {
    border-color: %(brand)s !important;
}

/* Odoo's own custom colour classes, generated from $o-text-colors-custom /
   $o-bg-colors-custom through the same o-print-color() mixin. .text-action is
   the one that shows: it colours the icons in the search dropdown. */
.text-action {
    --color: rgba(%(brand_rgb)s, var(--text-opacity, 1));
}

.bg-action {
    --background-color: rgba(%(brand_rgb)s, var(--bg-opacity, 1));
}

/* The checkmark on a selected dropdown item is a ::before whose colour is
   compiled from $link-color (webclient.scss), so the :root --link-color above
   cannot reach it. */
:not(.dropstart) > .dropdown-item.active:not(.dropdown-item_active_noarrow):before,
:not(.dropstart) > .dropdown-item.selected:not(.dropdown-item_active_noarrow):before {
    color: %(brand)s;
}

/* The status bar draws its current step with a ::before whose colour comes
   straight out of the button map -- a Carbon-blue literal -- so it kept a blue
   rim on a branded document. */
.o_field_statusbar > .o_statusbar_status {
    --o-statusbar-border-active: %(brand)s;
}

/* search_view.scss compiles `border-color: $input-focus-border-color` on
   focus, with no property behind it, so the bar recoloured its 1px border in
   Carbon blue. Carbon does not signal focus with a border at all -- it uses a
   single 2px inset ring, which components/search.scss now draws from
   --cds-focus -- so the border is held at the resting colour instead of being
   branded, which is what stopped it reading as a double outline. */
.o_searchview:focus-within,
.o_searchview:focus-within + .o_searchview_dropdown_toggler {
    border-color: var(--carbon-border-subtle);
}

/* .btn-link and .btn-light both carry the link colour: the theme maps
   .btn-light to Carbon's GHOST button, whose label is link-primary. Odoo uses
   it for the form's save and discard buttons, so without this those stay
   Carbon blue on a branded database -- along with the icons inside them, which
   inherit. */
.btn-link,
.btn-light {
    --btn-color: %(link)s;
    --btn-hover-color: %(link_hover)s;
    --btn-active-color: %(link_hover)s;
}

/* The theme's own button maps compile "active" to $c-border-interactive, a
   Carbon-blue literal, so an open dropdown or a pressed secondary button drew
   a blue rim on an otherwise branded UI. */
.btn-secondary,
.btn-outline-secondary,
.o-dropdown.btn-secondary {
    --btn-active-border-color: %(brand)s;
}

/* dropdown.scss compiles the open state straight out of the button map --
   `border-color: map-get($-value, 'active-border')` -- with no custom property
   behind it, so an open dropdown kept a Carbon-blue rim no matter what the
   brand was. Same specificity as Odoo's rule; this stylesheet simply loads
   after it. */
.o-dropdown.btn-secondary.show,
.o-dropdown.btn-outline-secondary.show {
    border-color: %(brand)s;
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
/* The header bar itself is the one declaration that has to be plain: Odoo
   compiles `.o_main_navbar { background: $o-navbar-background }` with no
   custom property behind it.
   
   Everything INSIDE the bar does have one. Odoo routes every navbar entry
   through --NavBar-* (navbar.scss), so re-pointing those is enough and no
   selector has to be enumerated. Without them the entries keep their compiled
   Carbon-shell colours and sit as opaque near-black blocks on a branded
   header -- which is exactly what a coloured header used to look like. */
.o_main_navbar {
    background-color: %(header_bg)s;
    border-bottom: 1px solid %(header_border)s;
    color: %(header_text)s;

    --NavBar-entry-backgroundColor: %(header_bg)s;
    --NavBar-entry-backgroundColor--hover: %(header_hover)s;
    --NavBar-entry-backgroundColor--focus: %(header_hover)s;
    --NavBar-entry-backgroundColor--active: %(header_active)s;
    --NavBar-entry-color: %(header_text_secondary)s;
    --NavBar-entry-color--hover: %(header_text)s;
    --NavBar-entry-color--active: %(header_text)s;
    --NavBar-brand-color: %(header_text)s;

    /* The theme's own header pieces -- the global search button, the apps
       toggle -- read these aliases, so they follow the brand too instead of
       staying on the Carbon shell tones. */
    --cds-shell-bg: %(header_bg)s;
    --cds-shell-text: %(header_text)s;
    --cds-shell-text-secondary: %(header_text_secondary)s;
    --cds-shell-hover: %(header_hover)s;
    --cds-shell-active: %(header_active)s;
}
"""
            % dict(palette, name=company.name)
        )
