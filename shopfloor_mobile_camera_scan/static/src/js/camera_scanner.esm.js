/**
 * Copyright 2026 Avunu LLC (avu.nu)
 * License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
 *
 * A singleton fullscreen camera scanner overlay for the Shopfloor mobile app.
 *
 *   import cameraScanner from "./camera_scanner.esm.js";
 *   cameraScanner.open((barcode) => { ... });   // opens the camera overlay
 *
 * The overlay decodes with the native BarcodeDetector API where available
 * (Android / desktop Chrome) and falls back to html5-qrcode — the engine that
 * actually runs on iPad Safari, which ships no BarcodeDetector.
 */

/*
 * Vendored (html5-qrcode 2.3.8, Apache-2.0 — see static/lib/html5-qrcode/).
 * Served from Odoo rather than a CDN: a workshop tablet is exactly the device
 * most likely to be on flaky wifi, and a strict Content-Security-Policy would
 * block the third-party origin outright. Both failures look identical to the
 * technician — the camera button does nothing.
 */
const HTML5_QRCODE_URL =
    "/shopfloor_mobile_camera_scan/static/lib/html5-qrcode/html5-qrcode.min.js";

const READER_ID = "sf-cam-reader";

function loadScript(src) {
    return new Promise(function (resolve, reject) {
        if (document.querySelector('script[src="' + src + '"]')) {
            resolve();
            return;
        }
        const s = document.createElement("script");
        s.src = src;
        s.onload = resolve;
        s.onerror = () => reject(new Error("Failed to load " + src));
        document.head.appendChild(s);
    });
}

/* ---- native BarcodeDetector engine (fast path) ---------------------- */
class NativeEngine {
    constructor(containerId, onDetect) {
        this.container = document.getElementById(containerId);
        this.onDetect = onDetect;
        this.video = null;
        this.stream = null;
        this.raf = null;
    }

    async start() {
        const formats = await window.BarcodeDetector.getSupportedFormats();
        this.detector = new window.BarcodeDetector({ formats });
        this.video = document.createElement("video");
        this.video.setAttribute("playsinline", "true");
        this.video.muted = true;
        this.video.className = "sf-cam-video";
        this.container.appendChild(this.video);
        this.stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: { ideal: "environment" } },
        });
        this.video.srcObject = this.stream;
        await this.video.play();
        this._tick();
    }

    async _tick() {
        if (!this.stream) {
            return;
        }
        try {
            const codes = await this.detector.detect(this.video);
            if (codes && codes.length) {
                this.onDetect(codes[0].rawValue);
            }
        } catch (e) {
            /* transient per-frame decode error */
        }
        this.raf = requestAnimationFrame(this._tick.bind(this));
    }

    async stop() {
        if (this.raf) {
            cancelAnimationFrame(this.raf);
            this.raf = null;
        }
        if (this.stream) {
            this.stream.getTracks().forEach((t) => t.stop());
            this.stream = null;
        }
        if (this.video) {
            this.video.srcObject = null;
            this.video.remove();
            this.video = null;
        }
    }
}

/* ---- html5-qrcode engine (the iPad path) ---------------------------- */
class Html5QrcodeEngine {
    constructor(containerId, onDetect) {
        this.containerId = containerId;
        this.onDetect = onDetect;
        this.instance = null;
        this.running = false;
    }

    async start() {
        if (!window.Html5Qrcode) {
            await loadScript(HTML5_QRCODE_URL);
        }
        this.instance = new window.Html5Qrcode(this.containerId, { verbose: false });
        await this.instance.start(
            { facingMode: "environment" },
            { fps: 10, qrbox: undefined },
            (decodedText) => this.onDetect(decodedText),
            function () {
                /* per-frame "not found" — ignore */
            }
        );
        this.running = true;
    }

    async stop() {
        if (this.instance && this.running) {
            try {
                await this.instance.stop();
            } catch (e) {
                /* already stopped */
            }
            try {
                this.instance.clear();
            } catch (e) {
                /* ignore */
            }
        }
        this.running = false;
        this.instance = null;
    }
}

/* ---- overlay controller (singleton) --------------------------------- */
class CameraScanner {
    constructor() {
        this.overlay = null;
        this.engine = null;
        this.onDetect = null;
        this._handling = false;
    }

    async open(onDetect) {
        if (this.overlay) {
            return; // already open
        }
        this.onDetect = onDetect;
        this._handling = false;
        this._buildOverlay();
        try {
            await this._startEngine();
        } catch (e) {
            this._setStatus("Camera unavailable: " + e.message);
        }
    }

    async close() {
        if (this.engine) {
            try {
                await this.engine.stop();
            } catch (e) {
                /* ignore */
            }
            this.engine = null;
        }
        if (this.overlay) {
            this.overlay.remove();
            this.overlay = null;
        }
    }

    _buildOverlay() {
        const o = document.createElement("div");
        o.className = "sf-cam-overlay";
        o.innerHTML =
            '<div class="sf-cam-topbar">' +
            '<span class="sf-cam-title">Scan barcode</span>' +
            '<button type="button" class="sf-cam-close" aria-label="Close">✕</button>' +
            "</div>" +
            '<div id="' +
            READER_ID +
            '" class="sf-cam-reader"></div>' +
            '<div class="sf-cam-frame"></div>' +
            '<div class="sf-cam-status">Starting camera…</div>';
        o.querySelector(".sf-cam-close").addEventListener("click", () => this.close());
        document.body.appendChild(o);
        this.overlay = o;
    }

    _setStatus(text) {
        if (this.overlay) {
            const s = this.overlay.querySelector(".sf-cam-status");
            if (s) {
                s.textContent = text;
            }
        }
    }

    async _startEngine() {
        const onFound = (code) => this._handle(code);
        this.engine =
            "BarcodeDetector" in window
                ? new NativeEngine(READER_ID, onFound)
                : new Html5QrcodeEngine(READER_ID, onFound);
        await this.engine.start();
        this._setStatus("Point the camera at a barcode");
    }

    _handle(code) {
        if (this._handling || !code) {
            return;
        }
        this._handling = true;
        if (navigator.vibrate) {
            navigator.vibrate(60);
        }
        const cb = this.onDetect;
        // Close first so the camera is released before the scenario advances.
        this.close();
        if (cb) {
            cb(code);
        }
    }
}

export default new CameraScanner();
