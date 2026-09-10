/**
 * Copyright 2026 Avunu LLC (avu.nu)
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
 */

import {translation_registry} from "/shopfloor_mobile_base/static/src/services/translation_registry.esm.js";
import {auth_handler_registry} from "/shopfloor_mobile_base/static/src/services/auth_handler_registry.esm.js";
import event_hub from "/shopfloor_mobile_base/static/src/services/event_hub.esm.js";
// Reused verbatim: an oauth-flavored app's ongoing REST calls carry the
// exact same API-KEY header as an api_key-flavored app, because the
// resolved key ends up in the same `$root.apikey` config-registry slot
// either way. Importing this also registers that "apikey" config-registry
// slot as a side effect, exactly as it does for the sibling module.
import {ApiKeyAuthHandler} from "/shopfloor_mobile_base_auth_api_key/static/src/login.esm.js";

auth_handler_registry.add("oauth", ApiKeyAuthHandler);

/**
 * Capture and strip the `#apikey=...` / `#oauth_error=...` fragment
 * SYNCHRONOUSLY, at module top-level - before the router (hash mode, so
 * `location.hash` *is* its own addressing scheme - confirmed by reading
 * router.esm.js, no `mode:` option passed to `VueRouter`) or main.esm.js's
 * root instance ever look at `location.hash`. This must not be deferred
 * into any Vue lifecycle hook, or the router will already have tried (and
 * failed) to resolve the fragment as a route.
 */
let _oauth_key = null;
let _oauth_error = null;
(function capture_oauth_fragment() {
    const match = /^#(apikey|oauth_error)=(.+)$/.exec(window.location.hash);
    if (!match) {
        return;
    }
    if (match[1] === "apikey") {
        _oauth_key = decodeURIComponent(match[2]);
    } else {
        _oauth_error = decodeURIComponent(match[2]);
    }
    window.history.replaceState(
        null,
        "",
        window.location.pathname + window.location.search
    );
})();

/**
 * Actually *applying* the captured key/error is deferred to the
 * `app:mounted` event - confirmed (by reading main.esm.js) to fire from
 * the root instance's own `mounted()` hook, the earliest point a root
 * instance with a working `login()`/router exists. `login-page`'s own
 * `mounted()` (which registers the `login:success` -> redirect-home
 * listener this depends on) runs first, since it's already rendered as
 * the router's initial view at this point and Vue mounts children before
 * their parent.
 */
event_hub.$on("app:mounted", function (root) {
    if (_oauth_key) {
        root.apikey = _oauth_key;
        root.login({preventDefault: function () {}});
    } else if (_oauth_error) {
        // `login-page`'s own `login:failure` listener (registered in its
        // `mounted()`, already run by this point) shows the same generic
        // invalid-login message a bad API key would; the specific error
        // code is only surfaced here, for anyone debugging a denial.
        console.warn("Shopfloor oauth login failed:", _oauth_error);
        root.trigger("login:failure", {root: root});
    }
});

/**
 * One button per `app_info.oauth_providers` entry (built server-side by
 * `shopfloor_app.py._make_oauth_providers()`), each a plain redirect out
 * to Google/Apple - no AJAX.
 *
 * Conventional name: `login-` + auth_type (from app config).
 */
Vue.component("login-oauth", {
    computed: {
        providers: function () {
            return this.$root.app_info.oauth_providers || [];
        },
    },
    template: `
    <div class="button-list button-vertical-list full">
        <v-row align="center" v-for="provider in providers" :key="provider.id">
            <v-col class="text-center" cols="12">
                <v-btn
                    :href="provider.auth_link"
                    color="primary"
                    block
                    class="login-oauth-btn"
                    style="position: relative;"
                >
                    <v-icon
                        v-if="provider.css_class"
                        :class="provider.css_class"
                        style="position: absolute; left: 16px; top: 50%; transform: translateY(-50%);"
                    />
                    <div style="display: flex; justify-content: center; width: 100%;">{{ provider.body }}</div>
                </v-btn>
            </v-col>
        </v-row>
        <v-row align="center" v-if="!providers.length">
            <v-col class="text-center" cols="12">
                {{ $t('screen.login.oauth_no_providers') }}
            </v-col>
        </v-row>
    </div>
    `,
});

translation_registry.add(
    "en-US.screen.login.oauth_no_providers",
    "No sign-in method is configured for this app yet. Ask an admin."
);
