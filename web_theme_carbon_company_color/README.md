# Carbon Backend Theme / Company Color

Glue between [`web_theme_carbon`](../web_theme_carbon) and OCA's
`web_company_color`. It installs itself (`auto_install`) once both are present,
so it is never something you have to go looking for.

## Why it is needed

`web_company_color` compiles a hardcoded SCSS template per company, stores the
result as an `ir.attachment`, and injects it into `web.webclient_bootstrap`
**after every other bundle** — with `!important` on nearly every declaration.

Left alone it does not tint the Carbon theme, it overwrites it: navbar, buttons,
links, search facets, the statusbar and the stat buttons all revert to its own
Odoo-flavoured palette, Odoo purple included.

So this module replaces the template rather than fighting it.

## What it does

The company's colours are re-expressed as **Carbon design tokens**, which the
theme's component CSS already reads. One colour then propagates coherently —
focus rings, selected rows, the notebook underline, the side-nav rule, the
statusbar current step — instead of only the handful of places the stock
template happens to name.

| Company field | Carbon role |
|---|---|
| `color_button_bg` | the whole **interactive** family: `--cds-interactive`, `--cds-focus`, `--cds-border-interactive`, `--cds-button-primary`, `.btn-primary` |
| `color_link_text` | `--cds-link-primary` (falls back to the primary) |
| `color_navbar_bg` | the UI Shell header |
| `*_hover`, `*_text`, `*_border_bottom` | honoured when set, otherwise derived |

Anything unset falls back to **Carbon's** own g10 value, so a company that sets
one colour gets a coherent palette rather than a mix of its brand and Odoo purple.

## Two things worth knowing

**No `!important` anywhere.** Buttons look like they would need it — Odoo
compiles them to literals from `$o-btns-bs-override` — but Bootstrap 5.3's
`button-variant()` writes `--btn-bg` / `--btn-hover-bg` / … and `.btn` reads
them back (Odoo sets `$variable-prefix` to `''`), so setting those custom
properties makes Bootstrap's own rules serve our values. The navbar is the one
surface that genuinely needs plain declarations, because the theme compiles it
from `$o-navbar-*` SCSS variables that no runtime property can reach.

**Shades are computed in Python, not with `darken()`.** Everything emitted here
is a custom property, and Sass does not evaluate functions inside a custom
property's value — it passes them through as plain CSS. `darken($c, 8%)` would
reach the browser as literal text, which is invalid and silently ignored, so
the hover state would just stop working with nothing in any log. `shade()`
resolves every colour before it reaches the template, and
`tests/test_company_color.py` fails if an unevaluated function ever reappears.

## Limitation

The company colour is applied in **both** light and dark, since it is a brand
colour. A very dark brand colour will therefore read poorly against Carbon's
g100 background, where Carbon's own palette would lighten the interactive tone
instead. If that matters, set a lighter brand colour or extend
`_scss_get_sanitized_values` to emit a `web.assets_web_dark`-only variant.
