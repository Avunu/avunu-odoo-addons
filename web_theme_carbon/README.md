# Carbon Backend Theme (`web_theme_carbon`)

IBM [Carbon Design System](https://carbondesignsystem.com/) styling for the Odoo 18 backend. Light theme is Carbon **g10**, dark is **g100**.

Almost entirely CSS: it restyles Odoo's existing markup rather than replacing it, because template drift is where Odoo upgrades actually break themes. Two features are the exception — see **Behaviour** below — and each is anchored on the most stable hook available.

## The one thing to know

**`static/lib/carbon/`, `static/src/scss/generated/` and `static/fonts/` are generated. Never edit them by hand.** Run `npm run codegen` instead.

They exist because **Odoo compiles SCSS with libsass 3.6.6**, which has no `@use`/`@forward`/`sass:*`, while `@carbon/styles` is written entirely in the Dart Sass module system. Carbon therefore cannot be compiled by Odoo at runtime; it is compiled here at build time and the output committed. This is a deliberate break from the usual "commit `.scss`, let Odoo compile it" convention.

The failure mode if you forget is nasty: libsass does not reject `@use`, it emits it verbatim as a literal at-rule and the import silently never happens.

## Layout

```
tools/                          build-time only; not needed at runtime
  gen-carbon-tokens.mjs         Carbon -> tokens, in the two forms Odoo needs
  gen-fonts.mjs                 vendors IBM Plex + generates @font-face
  audit.mjs                     drift guard (see below)
static/lib/carbon/*.css         GENERATED  :root { --cds-* }  one file per theme
static/fonts/                   GENERATED  IBM Plex woff2 + OFL licences
static/src/scss/
  generated/                    GENERATED  $c-* literals, @font-face
  bridge/                       hand-written  Carbon -> Odoo $o-*  (light)
  bridge_dark/                  hand-written  Carbon -> Odoo $o-*  (dark)
  components/                   hand-written  Odoo selectors -> var(--cds-*)
```

Everything hand-written is plain libsass SCSS that Odoo still compiles at runtime, so the normal edit-and-reload loop is unchanged for the code you actually iterate on.

## Why tokens exist twice

Carbon values are emitted **both** as `--cds-*` custom properties and as `$c-*` SCSS literals, from one Dart Sass run so they cannot drift.

The literals are not a convenience. Odoo runs its `$o-*` variables through Sass colour maths — `darken()`, `mix()`, `invert()`, `lighten(saturate(adjust-hue()))` — and `$o-caret-down` does `str-slice(#{$o-main-text-color}, 2)` to build an SVG data-URI. A `var(--cds-text-primary)` there yields the string `ar(--cds-text-primary)`.

So: **the bridge uses literals; component CSS uses `var(--cds-*)`** and gets dark mode for free.

## Dark mode, and the asymmetry it forces

Odoo's dark mode is a **server-side bundle swap** on the `color_scheme` cookie, not a class or `data-theme` flip. `web.assets_web_dark` includes `web.assets_web` first and appends after it, which cuts both ways in the same bundle:

-   **CSS custom properties** win by being **appended last** — so `carbon.g100.css` goes at the back and overrides `carbon.g10.css` by cascade.
-   **SCSS variables** are resolved at compile time and consumed early, so they must be spliced in with `('before', ...)` at the **front**.

Hence the inverted `!default` rule, which `tools/audit.mjs` enforces:

|  | !default? | why |
| --- | --- | --- |
| bridge/ | always | assets_web_print loads primary_variables_print.scss first and print's values must survive |
| bridge_dark/ | never | the light bridge has already bound every name; a !default here makes dark a silent no-op |

Dark mode needs **`web_dark_mode`** (an AGPL-3 OCA module), which owns the cookie and the user-menu toggle. Community Odoo has no way to reach dark mode without it, and that dependency is what makes this module AGPL-3. (`web_responsive` is LGPL-3 and does not force it.)

## Commands

```sh
npm install --ignore-scripts        # IBM_TELEMETRY_DISABLED=true in CI
npm run codegen                     # regenerate everything
npm run audit                       # drift guard, warn-only
npm run check                       # codegen --check + audit --strict   <- CI

odoo -u web_theme_carbon --test-enable --stop-after-init   # cascade tests
```

`npm run check` regenerates in memory and byte-compares, so it fails when the committed output is stale without touching the tree.

## What is styled

Bridge (variables only, no bespoke CSS): palette, gray ramp, IBM Plex type scale,
square corners, the full `$o-btns-bs-override` button hierarchy, navbar, control
panel, kanban, notification and burger tokens, and web_responsive's `$app-menu-*`.

Components: list view (`cds--data-table`), fields, form sheet, statusbar
(`cds--content-switcher`), notebook (`cds--tabs`), stat buttons, navbar
(`cds--header`), control panel, search bar and panel, apps grid, dialogs
(`cds--modal`), dropdowns (`cds--menu`), notifications, tags and status badges
(`cds--tag`) and kanban records (`cds--tile`).

## Behaviour

Two Carbon patterns Odoo has no equivalent for. These are the only parts of the theme that are not pure CSS, so each is anchored on the most stable hook available and the cost of it breaking is stated.

**Global search in the header** (Carbon UI Shell). Odoo's global search is the command palette, reachable only by Ctrl+K, which nobody discovers on their own. The header button opens that same palette rather than introducing a second search — in its **menus** mode (the `/` namespace: every app and menu item, fuzzy matched), which is the comprehensive "take me anywhere" search and what the apps switcher uses. Ctrl+K keeps the default command mode, a HUD of the actions on the current screen, for people who know it is there. Registered as a **systray item**, which the navbar renders straight from a registry — so there is no template inheritance here at all, and nothing to drift.

**Search on tables** (Carbon data-table toolbar). Filters the rows on screen, which is what Carbon's table search does and what Odoo's control-panel search does not — that one changes the domain and re-queries.

Scope differs by list type, deliberately:

> **x2many lists inside a form** — the whole relation is searched. An `ir.model` form lists hundreds of fields forty at a time, and a search that cannot see past the current page will not find the field you want, which is the case this exists for. The relation is pulled in once per search (its ids are already known client-side), capped at 2000 records, and the original pagination is restored when the query is cleared.
>
> **View lists** — the loaded page only. Their record set is a server-side domain that could be millions of rows, so nothing is pre-loaded; the control-panel search is the right tool there and still works normally.

Either way the toolbar shows `n of m` while a query is active, because the difference matters and should not have to be inferred. Hidden on grouped lists, where group counts would silently disagree with what is shown.

Rows are **hidden, not removed**: `ListRenderer` renders `list.records` straight from the model, and filtering that array would corrupt selection, keyboard navigation, editing and the aggregate footer. Instead it patches `getRowClass()`, which the row template already calls, so the model is untouched and the row markup is never referenced.

Its two upstream dependencies are `ListRenderer.getRowClass()` and one xpath on the `<table>` element in `web.ListRenderer`. That xpath deliberately targets the element and **not** `hasclass('o_list_table')`: the table carries `t-attf-class`, so it has no static class attribute, `hasclass()` never matches, and the inheritance then throws at template-compile time — taking the whole list view down with it.

## Brand colours

**Settings → Companies → _(company)_ → Carbon Theme**, per company.

The brand colour is not a header tint. It sets Carbon's *interactive* role, so
one value reaches primary buttons, links, focus rings, selected rows, active
tabs, the status bar and the search-panel rule — everywhere the theme draws on
`--cds-interactive`. The header is configured separately, because tinting the
bar and rebranding the controls are different decisions.

**Light and dark are separate fields on purpose.** Carbon does not reuse one
interactive tone across themes: its own is Blue 60 `#0f62fe` on g10 and the
lighter Blue 50 `#4589ff` on g100, because a mid-dark colour that reads well on
`#f4f4f4` does not carry against `#161616`. Set only the light one and the dark
variant is derived by lightening it; set both to control each exactly.

Setting a header colour re-points Odoo's `--NavBar-*` custom properties as well as the bar itself, so the menu entries, their hover and active states and their labels all follow it. Without that they keep the compiled Carbon-shell tones and sit as opaque near-black blocks on a branded bar.

Hover, active and text-on-brand are derived too — hover darkens in light and
brightens in dark, and the label flips between near-black and near-white for
contrast. Anything left empty falls back to Carbon's own value, so a company
that sets one colour still gets a coherent palette.

Nothing is emitted at all until a company sets something.

### How it is delivered

A `<style>` block injected into the webclient head *after* the asset bundles —
not a generated stylesheet. Every value is a CSS custom property, so nothing
needs compiling, and since Odoo picks the theme server-side only the variant in
use is emitted.

It needs no `!important`. Buttons look like they would: Odoo compiles `.btn-*`
to literals from `$o-btns-bs-override`. But Bootstrap 5.3's `button-variant()`
writes `--btn-bg` / `--btn-hover-bg` / … and `.btn` reads them back (Odoo sets
`$variable-prefix` to `''`), so setting those properties makes Bootstrap's own
rules serve our values. The header is the one surface needing plain
declarations, since the theme compiles it from `$o-navbar-*`.

Shades are computed in Python rather than emitted as `darken()`: these are
custom property values, and Sass does not evaluate functions inside them — a
function would reach the browser as literal text and be silently ignored.

> Not compatible with OCA's `web_company_color`. That module injects its own
> palette as `!important` CSS after every bundle and overwrites the theme
> wholesale; this replaces it rather than coexisting with it.

## The drift guard

Every check in `tools/audit.mjs` guards a failure that is **silent** — the theme keeps loading and one surface quietly reverts to stock Odoo:

1.  no Dart-Sass-only syntax in shipped SCSS
2.  no `var()` reaches an SCSS variable assignment
3.  the inverted `!default` policy above
4.  every theme-dependent light value is restated in dark
5.  every `$c-*` reference resolves, in both themes
6.  variables Odoo `str-slice()`s are 6-digit hex (Carbon has real `rgba()` tokens)
7.  the `('before', ...)` anchors and bridged `$o-*` still exist — checked against **both v18 and v19**, so v19 drift shows up before the port
8.  `web_responsive`'s `$app-menu-*` are still `!default` (we win by loading earlier, which only works while they are)

Point 7 is the sharp one: an anchor that stops resolving does not degrade gracefully. `AssetPaths.index()` raises `ValueError` and every backend page 500s.

Cascade conflicts are checked separately, in `tests/test_cascade.py`, because
deciding them honestly needs the compiled bundle: Odoo marks declarations
`!important` from inside mixins, so a static SCSS scan produced false alarms that
the compiled bundle disproved, and a guard that cries wolf gets ignored.

## Scope

Not attempted, deliberately: Carbon's icon set (Carbon ships SVG, Odoo uses an icon font — CSS cannot swap glyph shapes), and the UI Shell restructure (that needs template surgery). Carbon's own component CSS is **not** shipped: without `.cds--*` classes in Odoo's DOM it would be 60–80 KB per component matching nothing.
