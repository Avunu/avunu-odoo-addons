/** @odoo-module **/
/**
 * Carbon UI Shell global search, in the header.
 *
 * Carbon's shell puts a search affordance in the header's global actions, and
 * Odoo has no visible one -- its global search is the command palette, reachable
 * only by Ctrl+K, which is undiscoverable for anyone who has not been told.
 *
 * So this surfaces the search that already exists rather than building a second
 * one: the button opens the command palette, which already searches menus,
 * records and actions and already knows how to rank them.
 *
 * WHICH MODE. The palette has namespaces, and the default one -- what Ctrl+K
 * opens -- is the command list: a HUD of the actions available on the current
 * screen. The `/` namespace is the menus one, provided by
 * webclient/menus/menu_providers.js: every app and every menu item, fuzzy
 * matched. That is the comprehensive "take me anywhere" search, it is what
 * web_responsive opens from the apps switcher, and it is what a search button
 * in the header should mean. Ctrl+K keeps the command HUD for people who know
 * it is there, and typing `/` in it reaches this mode anyway.
 *
 * Registered as a systray item rather than patched into web.NavBar. The navbar
 * renders `systrayItems` straight from the registry, so no template inheritance
 * is needed and there is nothing here to drift when the navbar markup changes.
 */
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class CarbonHeaderSearch extends Component {
    static template = "web_theme_carbon.HeaderSearch";
    static props = {};

    setup() {
        this.command = useService("command");
    }

    get title() {
        // The keyboard path belongs in the tooltip: the point of the button is
        // to advertise something most people never discover.
        return _t("Search menus and apps (CTRL+K, then /)");
    }

    onClick() {
        // "/" selects the menus namespace; see the note at the top.
        this.command.openMainPalette({ searchValue: "/" });
    }
}

export const systrayItem = { Component: CarbonHeaderSearch };

// The navbar reverses the registry order, so a HIGH sequence renders leftmost.
// Carbon puts search first among the header's global actions.
registry.category("systray").add("web_theme_carbon.search", systrayItem, { sequence: 100 });
