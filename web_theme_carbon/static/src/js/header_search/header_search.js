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
        // The hotkey belongs in the tooltip: the point of the button is to
        // advertise a shortcut most people never discover.
        return _t("Search (CTRL+K)");
    }

    onClick() {
        this.command.openMainPalette();
    }
}

export const systrayItem = { Component: CarbonHeaderSearch };

// The navbar reverses the registry order, so a HIGH sequence renders leftmost.
// Carbon puts search first among the header's global actions.
registry.category("systray").add("web_theme_carbon.search", systrayItem, { sequence: 100 });
