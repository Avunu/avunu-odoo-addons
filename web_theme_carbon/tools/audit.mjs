#!/usr/bin/env node
/**
 * Drift guard.
 *
 * Everything checked here fails the SAME silent way: the theme keeps loading,
 * the bundle still compiles, and one surface quietly reverts to stock Odoo --
 * or, worse, the dark theme stops applying and nobody notices until someone
 * toggles it. None of this is caught by "does it compile".
 *
 *   node tools/audit.mjs            warn only  (exit 0)
 *   node tools/audit.mjs --strict   fail       (exit 1)
 *
 * ODOO_PATH / ODOO19_PATH point at Odoo checkouts; the Odoo-side checks skip
 * with a note when they are absent, so the Carbon-side checks still run in CI.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const STRICT = process.argv.includes("--strict");
const ODOO = process.env.ODOO_PATH || "/home/batonac/Development/odoo-v18";
const ODOO19 = process.env.ODOO19_PATH || "/home/batonac/Development/odoo-v19";
const WEB_RESPONSIVE = process.env.OCA_WEB_PATH ||
  "/home/batonac/Development/odoo-project-sandbox/modules/web";

let failures = 0;
const fail = (msg) => { console.error(`  FAIL  ${msg}`); failures++; };
const ok = (msg) => console.log(`  ok    ${msg}`);

const read = (p) => fs.readFileSync(p, "utf8");
/** Comments carry prose like "$c-button-* were rebound", which a bare regex
 *  scan happily mistakes for a real reference. They also end statements: a
 *  TRAILING `// #262626` after an assignment used to swallow the next one,
 *  which made restated dark variables look missing. Strip both forms, but stay
 *  out of quoted strings so a "https://" in a value survives. */
function code(p) {
  const noBlock = read(p).replace(/\/\*[\s\S]*?\*\//g, "");
  return noBlock.split("\n").map((line) => {
    let q = null;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (q) { if (ch === q && line[i - 1] !== "\\") q = null; continue; }
      if (ch === '"' || ch === "'") { q = ch; continue; }
      if (ch === "/" && line[i + 1] === "/") return line.slice(0, i);
    }
    return line;
  }).join("\n");
}
/** SCSS assignments can span many lines -- a map literal carries its !default
 *  on the CLOSING line -- so split on top-level `;`, not on newlines. */
function assignments(src) {
  const out = [];
  let depth = 0, buf = "";
  for (const ch of src) {
    if (ch === "(") depth++;
    if (ch === ")") depth--;
    if (ch === ";" && depth === 0) { out.push(buf.trim()); buf = ""; continue; }
    buf += ch;
  }
  return out.filter((st) => /^\$[\w-]+\s*:/.test(st));
}
/** Odoo declares a handful of variables WITHOUT !default; an earlier
 *  assignment would just be overwritten, so bridge/late.scss has to hard-assign
 *  them. They are geometry, never colour. */
const HARD_ASSIGN_OK = new Set([
  "$o-search-panel-width", "$o-search-panel-font-size", "$o-statusbar-arrow-width",
  "$o-search-bar-facet-value-width", "$o-field-translate-padding",
  "$o-form-renderer-max-width", "$o-form-view-sheet-max-width",
  "$o-form-separator-color",
]);
const walk = (d) => fs.existsSync(d)
  ? fs.readdirSync(d, { withFileTypes: true }).flatMap((e) =>
      e.isDirectory() ? walk(path.join(d, e.name)) : [path.join(d, e.name)])
  : [];

const S = path.join(ROOT, "static/src/scss");
const scssFiles = walk(S).filter((f) => f.endsWith(".scss"));
const bridgeLight = walk(path.join(S, "bridge")).filter((f) => f.endsWith(".scss"));
const bridgeDark = walk(path.join(S, "bridge_dark")).filter((f) => f.endsWith(".scss"));
const tokensLight = path.join(S, "generated/_carbon_tokens.scss");
const tokensDark = path.join(S, "generated/_carbon_tokens_dark.scss");

// -- 1. libsass safety -------------------------------------------------------
// Odoo compiles this SCSS with libsass 3.6.6. It does not merely reject Dart
// Sass module syntax -- a bare `@use` is passed through as a literal at-rule
// and the import silently never happens, so the failure looks like a caching
// problem rather than an error.
console.log("\n[1] libsass safety (no Dart-Sass-only syntax in shipped SCSS)");
{
  const banned = [/^\s*@use\s/m, /^\s*@forward\s/m, /\bsass:[a-z]+/, /\bmath\.div\(/,
                  /\bmap\.get\(/, /\bcolor\.adjust\(/];
  let bad = 0;
  for (const f of scssFiles) {
    const src = read(f);
    for (const re of banned) {
      if (re.test(src)) { fail(`${path.relative(ROOT, f)} contains ${re}`); bad++; }
    }
  }
  if (!bad) ok(`${scssFiles.length} SCSS files are libsass-safe`);
}

// -- 2. the bridge must be literals ------------------------------------------
// $o-caret-down does str-slice(#{$o-main-text-color}, 2) to build an SVG
// data-URI; primary_variables.scss mix()es $o-action and
// lighten(saturate(adjust-hue($o-info))); secondary_variables.scss invert()s
// $o-view-background-color. A var(--cds-*) in any of those is silent garbage.
console.log("\n[2] bridge carries literals, never var(--cds-*)");
{
  let bad = 0;
  for (const f of [...bridgeLight, ...bridgeDark]) {
    read(f).split("\n").forEach((line, i) => {
      if (/^\s*\$[\w-]+\s*:/.test(line) && line.includes("var(--")) {
        fail(`${path.relative(ROOT, f)}:${i + 1} assigns a var() to an SCSS variable`);
        bad++;
      }
    });
  }
  if (!bad) ok("no var() reaches an SCSS variable assignment");
}

// -- 3. the inverted !default policy -----------------------------------------
// bridge/ MUST be all !default: assets_web_print loads
// primary_variables_print.scss before it, and print's values have to survive.
// bridge_dark/ MUST have none: the light bridge has already bound every name
// by the time it runs, so a !default there makes the dark theme a no-op.
console.log("\n[3] !default policy (inverted between light and dark)");
{
  let bad = 0;
  for (const f of bridgeLight) {
    for (const st of assignments(code(f))) {
      const name = st.match(/^(\$[\w-]+)/)[1];
      if (HARD_ASSIGN_OK.has(name)) continue;   // documented, intentional
      if (!st.includes("!default")) {
        fail(`${path.relative(ROOT, f)}: missing !default -> ${name}`);
        bad++;
      }
    }
  }
  for (const f of bridgeDark) {
    for (const st of assignments(code(f))) {
      if (st.includes("!default")) {
        fail(`${path.relative(ROOT, f)}: has !default (dark must hard-assign) -> ${st.match(/^(\$[\w-]+)/)[1]}`);
        bad++;
      }
    }
  }
  if (!bad) ok("light bridge is all !default; dark bridge has none");
}

// -- 4. light and dark bridges cover the same names --------------------------
// A name set only in the light bridge keeps its light value in dark mode.
console.log("\n[4] every theme-dependent light value is restated in dark");
{
  // Name-based heuristics get this wrong in both directions. The precise
  // question is whether a value CHANGES between themes, and that is knowable:
  // it does exactly when it reads a $c-* token. `none`, `transparent`, a
  // literal px and the always-dark shell palette are theme-invariant, so the
  // light assignment stands for both bundles and must NOT be restated.
  const assignedTokens = (files) => {
    const m = new Map();
    for (const f of files) {
      for (const st of assignments(code(f))) {
        m.set(st.match(/^(\$[\w-]+)/)[1], st);
      }
    }
    return m;
  };
  const L = assignedTokens(bridgeLight), D = assignedTokens(bridgeDark);
  const themeDependent = [...L].filter(([, st]) =>
    /\$c-[\w-]+/.test(st) && !/^\s*\$[\w-]+\s*:\s*\$c-shell-/.test(st));
  const missing = themeDependent.filter(([n]) => !D.has(n)).map(([n]) => n);
  if (missing.length) {
    fail(`${missing.length} theme-dependent var(s) never restated in dark: ${missing.slice(0, 10).join(", ")}`);
  } else {
    ok(`${themeDependent.length} theme-dependent vars all restated in dark (light ${L.size} / dark ${D.size})`);
  }
}

// -- 5. every $c-* referenced is defined, in BOTH token files ----------------
console.log("\n[5] $c-* references resolve in both themes");
{
  const defined = (f) => new Set(
    [...read(f).matchAll(/^\$(c-[\w-]+)\s*:/gm)].map((m) => m[1]));
  const L = defined(tokensLight), D = defined(tokensDark);
  const used = new Set();
  for (const f of [...bridgeLight, ...bridgeDark]) {
    for (const m of code(f).matchAll(/\$(c-[\w-]+)/g)) used.add(m[1]);
  }
  const missL = [...used].filter((n) => !L.has(n));
  const missD = [...used].filter((n) => !D.has(n));
  if (missL.length) fail(`undefined in light tokens: ${missL.join(", ")}`);
  if (missD.length) fail(`undefined in dark tokens: ${missD.join(", ")}`);
  if (L.size !== D.size) fail(`token name sets differ: light ${L.size} vs dark ${D.size}`);
  if (!missL.length && !missD.length && L.size === D.size)
    ok(`${used.size} referenced tokens all defined in both (${L.size} each)`);
}

// -- 6. hex-ness where Odoo string-slices ------------------------------------
// str-slice(#{rgba(22,22,22,.25)}, 2) yields "gba(22, 22, 22, 0.25)" inside an
// SVG data-URI. --cds-text-placeholder and --cds-text-disabled really are
// rgba() in Carbon, so this is a live hazard, not a theoretical one.
console.log("\n[6] variables Odoo string-slices are 6-digit hex");
{
  const LITERAL_ONLY = ["$o-main-text-color"];
  let bad = 0;
  for (const [file, files] of [["light", bridgeLight], ["dark", bridgeDark]]) {
    const src = files.map(read).join("\n");
    const tokens = read(files === bridgeLight ? tokensLight : tokensDark);
    for (const v of LITERAL_ONLY) {
      const m = src.match(new RegExp(`^\\s*\\${v}\\s*:\\s*\\$(c-[\\w-]+)`, "m"));
      if (!m) { fail(`${file}: ${v} not assigned`); bad++; continue; }
      const t = tokens.match(new RegExp(`^\\$${m[1]}\\s*:\\s*([^;]+);`, "m"));
      const val = t ? t[1].replace("!default", "").trim() : null;
      if (!val || !/^#[0-9a-f]{6}$/i.test(val)) {
        fail(`${file}: ${v} -> $${m[1]} = ${val ?? "?"} (must be #rrggbb)`);
        bad++;
      }
    }
  }
  if (!bad) ok("every string-sliced variable resolves to #rrggbb");
}

// -- 7. Odoo-side anchors and variables --------------------------------------
// An anchor that stops resolving is NOT a cosmetic regression: AssetPaths.index
// raises ValueError and every backend page 500s.
const ANCHORS = [
  "addons/web/static/src/scss/primary_variables.scss",
  "addons/web/static/src/scss/secondary_variables.scss",
  "addons/web/static/src/scss/bootstrap_overridden.scss",
];
for (const [label, base] of [["v18", ODOO], ["v19", ODOO19]]) {
  console.log(`\n[7-${label}] Odoo ${label} anchors and bridged variables`);
  if (!fs.existsSync(base)) { console.log(`  skip  ${base} not present`); continue; }
  for (const a of ANCHORS) {
    if (!fs.existsSync(path.join(base, a))) fail(`${label}: anchor missing -> ${a} (this 500s the backend)`);
  }
  const odooVars = new Set();
  for (const f of walk(path.join(base, "addons/web/static/src")).filter((f) => f.endsWith(".scss"))) {
    for (const m of read(f).matchAll(/^\s*(\$[\w-]+)\s*:/gm)) odooVars.add(m[1]);
  }
  const ours = new Set(bridgeLight.flatMap((f) =>
    [...read(f).matchAll(/^\s*(\$o-[\w-]+)\s*:/gm)].map((m) => m[1])));
  const gone = [...ours].filter((n) => !odooVars.has(n));
  if (gone.length) fail(`${label}: we override ${gone.length} var(s) Odoo no longer declares: ${gone.join(", ")}`);
  else ok(`${label}: all ${ours.size} bridged $o-* still declared by Odoo`);
}

// -- 8. web_responsive's app-menu vars ---------------------------------------
console.log("\n[8] web_responsive $app-menu-* still declared and still !default");
{
  const f = path.join(WEB_RESPONSIVE, "web_responsive/static/src/legacy/scss/primary_variable.scss");
  if (!fs.existsSync(f)) console.log(`  skip  ${f} not present`);
  else {
    const src = read(f);
    const ours = [...read(path.join(S, "bridge/primary_variables.scss"))
      .matchAll(/^\s*(\$app-menu-[\w-]+)\s*:/gm)].map((m) => m[1]);
    let bad = 0;
    for (const n of ours) {
      const re = new RegExp(`^\\s*\\${n}\\s*:[\\s\\S]*?!default`, "m");
      if (!src.includes(n)) { fail(`${n} no longer declared by web_responsive`); bad++; }
      // We win by loading EARLIER, which only works while theirs is !default.
      else if (!re.test(src)) { fail(`${n} is no longer !default in web_responsive`); bad++; }
    }
    if (!bad) ok(`${ours.length} $app-menu-* vars still !default upstream`);
  }
}

console.log(
  failures === 0
    ? "\nAudit passed."
    : `\nAudit found ${failures} issue(s).${STRICT ? "" : " (warn-only; use --strict to fail)"}`);
process.exit(STRICT && failures ? 1 : 0);
