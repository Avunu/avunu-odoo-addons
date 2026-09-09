# Carbon Backend Theme (`web_theme_carbon`)

IBM [Carbon Design System](https://carbondesignsystem.com/) styling for the Odoo 18 backend. Light theme is Carbon **g10**, dark is **g100**.

CSS-only: it restyles Odoo's existing markup and does not override a single QWeb template or patch an OWL component. That is deliberate — template drift is where Odoo upgrades actually break themes, and it keeps the port to v19 cheap.

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
(`cds--modal`), dropdowns (`cds--menu`), notifications, tags (`cds--tag`) and
kanban records (`cds--tile`).

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
