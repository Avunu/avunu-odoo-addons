# Shopfloor Mobile — Camera Scanning

Adds **device-camera barcode scanning** to the OCA **Shopfloor** mobile app,
without replacing it. Every scenario's search bar (reception, single product
transfer, cluster picking, checkout, …) gains a camera button. A camera scan is
delivered through the **exact same code path** as a hardware wedge scanner, so
no scenario needs to be modified.

This is the "augment Shopfloor" counterpart to the standalone
`stock_camera_scanner` PoC.

## How it hooks in

Shopfloor's mobile frontend is a standalone Vue 2 PWA. Every screen embeds the
one global `searchbar` component, which emits a `found` event that scenarios
handle via `@found="on_scan"`. This module hooks that single seam:

```
camera → decode barcode ──► searchbar.$emit("found", {text, type}) ──► scenario on_scan()
                                     ▲ identical to a wedge/keyboard scan
```

- **[templates/assets.xml](templates/assets.xml)** — inherits
  `shopfloor_mobile_base.shopfloor_app_assets` and injects our JS/CSS right
  before the main app script (so the override registers before the Vue root
  mounts).
- **[static/src/js/searchbar_camera.esm.js](static/src/js/searchbar_camera.esm.js)**
  — extends the global `searchbar` component (`Vue.component("searchbar")`),
  adding a `mdi-barcode-scan` button. On decode it calls
  `this.$emit("found", {text, type})` — byte-for-byte what the wedge path emits.
- **[static/src/js/camera_scanner.esm.js](static/src/js/camera_scanner.esm.js)**
  — a singleton fullscreen camera overlay. Uses the native `BarcodeDetector`
  API where present, and falls back to **html5-qrcode** (the engine that runs on
  iPad Safari).
- **[static/src/css/camera_scan.css](static/src/css/camera_scan.css)** — button
  + overlay styling with safe-area insets for iPad.

Because the override targets the *global* component, the camera button appears
on **all scenarios automatically** — including third-party ones — with zero
per-scenario code.

## Install & try

```bash
odoo -d odoo_dev -i shopfloor_mobile_camera_scan
```

You need a working Shopfloor mobile app first (`shopfloor_mobile_base` +
scenarios such as `shopfloor_reception_mobile`, configured with a profile,
menus and an API key — see the Shopfloor docs). Then open the Shopfloor app on
the iPad, enter any scenario, and tap the camera icon in the search bar.

- Camera access requires **HTTPS or `localhost`** — serve the app over TLS or an
  SSH tunnel, or Safari will silently block `getUserMedia`.
- Add the app to the iPad Home Screen for a full-screen, chrome-less feel.

## Scope / notes (PoC)

- The searchbar **template is copied** from `shopfloor_mobile_base 18.0.1.2.1`
  and augmented. If upstream changes that template, re-sync the copy in
  `searchbar_camera.esm.js` (it's ~15 lines).
- html5-qrcode is **vendored** under `static/lib/html5-qrcode/` (v2.3.8,
  Apache-2.0) and served from Odoo, so the scanner keeps working on flaky
  workshop wifi and under a strict CSP.
- No GS1 / AI parsing here — the raw decoded string is passed through. Combine
  with `shopfloor_gs1` if you need GS1 handling; parsing happens server-side and
  is unaffected by how the barcode was captured.
- Native `BarcodeDetector` (Android/desktop Chrome) and html5-qrcode may support
  slightly different symbologies; the overlay requests all formats each engine
  offers.
