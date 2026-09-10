/**
 * Copyright 2026 Avunu LLC (avu.nu)
 * License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
 *
 * Extend the global Shopfloor `searchbar` component to add a camera-scan
 * button. A camera scan emits the SAME `found` event a wedge/keyboard scan
 * emits, so every scenario's `@found="on_scan"` handler works unchanged —
 * no scenario edits required.
 *
 * The template below is copied from shopfloor_mobile_base 18.0.1.2.1 and
 * augmented with the camera button. If the upstream searchbar template
 * changes, re-sync this copy.
 */
import cameraScanner from "./camera_scanner.esm.js";

const BaseSearchbar = Vue.component("searchbar");

if (!BaseSearchbar) {
    // Ordering guarantees this shouldn't happen, but fail loudly if it does.
    // eslint-disable-next-line no-console
    console.error(
        "[shopfloor_mobile_camera_scan] global 'searchbar' component not found; " +
            "camera button not injected."
    );
} else {
    Vue.component(
        "searchbar",
        BaseSearchbar.extend({
            methods: {
                sfcOpenCamera: function () {
                    cameraScanner.open((code) => this.sfcOnCameraScan(code));
                },
                sfcOnCameraScan: function (code) {
                    if (!code) {
                        return;
                    }
                    const text = this.autotrim ? String(code).trim() : code;
                    // Mirror searchbar.search(): hand the value to the parent
                    // screen exactly as a typed/wedge scan would.
                    this.$emit("found", { text: text, type: this.input_data_type });
                    if (this.reset_on_submit && this.reset) {
                        this.reset();
                    }
                },
            },
            template: `
  <v-form
      v-on:submit="on_submit"
      :data-type="input_data_type"
      class="searchform sf-has-camera"
      >
    <div class="searchbar v-input v-text-field">
      <label class="v-label" v-if="input_label">{{ input_label }}</label>
      <input
        ref="searchbar"
        required v-model="entered"
        :type="input_type"
        :inputmode="autofocus ? 'none' : input_inputmode"
        :placeholder="input_placeholder"
        :autofocus="autofocus ? 'autofocus' : null"
        :autocomplete="autocomplete"
        @focus="onfocus"
        @blur="onblur"
        @click="onclick"
        />
      <button
        type="button"
        class="sf-camera-btn"
        aria-label="Scan with camera"
        @click.prevent.stop="sfcOpenCamera"
        >
        <i class="mdi mdi-barcode-scan"></i>
      </button>
      </div>
  </v-form>
  `,
        })
    );
}
