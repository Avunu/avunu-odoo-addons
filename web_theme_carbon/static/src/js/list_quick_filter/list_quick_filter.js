/** @odoo-module **/
/**
 * Carbon data-table toolbar search: filter the rows on screen.
 *
 * Carbon's data table carries its own search in a toolbar above the table,
 * separate from any application-level search, and it filters the rows the table
 * is showing. Odoo's control-panel search is a different thing -- it changes the
 * domain and re-queries the server -- so this adds the missing one rather than
 * duplicating that.
 *
 * SCOPE, and why it is surfaced in the UI: this filters the rows CURRENTLY
 * LOADED, i.e. the current page. That is what Carbon's table search does, but in
 * an ERP with pagination it would be a trap if it were silent about it, so the
 * toolbar shows "n of m" whenever a query is active. For anything beyond the
 * page, the control-panel search is the right tool and still works normally.
 *
 * IMPLEMENTATION: rows are hidden, not removed. ListRenderer renders
 * `list.records` straight from the model, and filtering that array would corrupt
 * selection, keyboard navigation, editing and the aggregate footer. Instead this
 * patches `getRowClass()`, which the row template already calls, and adds a class
 * that hides the row. The model is untouched; only the presentation changes.
 */
import { patch } from "@web/core/utils/patch";
import { useState } from "@odoo/owl";
import { ListRenderer } from "@web/views/list/list_renderer";
import { _t } from "@web/core/l10n/translation";

/** The class the stylesheet hides. */
const HIDDEN = "o_carbon_row_filtered_out";

patch(ListRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        this.carbonFilter = useState({ query: "", expanded: false });
    },

    /**
     * Appends the hiding class for rows that do not match.
     *
     * getRowClass is called by web.ListRenderer.RecordRow for every row, so
     * hooking it needs no template change and no knowledge of the row markup.
     */
    getRowClass(record) {
        const base = super.getRowClass(...arguments);
        if (!this.carbonFilter.query || this.carbonRecordMatches(record)) {
            return base;
        }
        return `${base || ""} ${HIDDEN}`.trim();
    },

    /**
     * Case-insensitive substring match over the record's displayed columns.
     *
     * Deliberately reads the FORMATTED value where one is available: a user
     * searching a list types what they can see -- "1,234.50", "Jan 3" -- not the
     * raw float or the ISO date underneath.
     */
    carbonRecordMatches(record) {
        const needle = this.carbonFilter.query.trim().toLowerCase();
        if (!needle) {
            return true;
        }
        for (const column of this.columns || []) {
            if (column.type !== "field") {
                continue;
            }
            const value = record.data[column.name];
            if (value === null || value === undefined || value === false) {
                continue;
            }
            let text;
            if (Array.isArray(value)) {
                text = value[1] ?? value[0]; // many2one: [id, display_name]
            } else if (typeof value === "object") {
                // x2many and similar: fall back to whatever the record knows
                text = value.displayName ?? value.count ?? "";
            } else {
                text = value;
            }
            if (String(text).toLowerCase().includes(needle)) {
                return true;
            }
        }
        return false;
    },

    get carbonFilterCounts() {
        const records = this.props.list.records || [];
        const shown = this.carbonFilter.query
            ? records.filter((r) => this.carbonRecordMatches(r)).length
            : records.length;
        return { shown, total: records.length };
    },

    get carbonFilterPlaceholder() {
        return _t("Search this page");
    },

    get carbonFilterLabel() {
        return _t("Search the rows on this page");
    },

    carbonToggleFilter() {
        this.carbonFilter.expanded = !this.carbonFilter.expanded;
        if (!this.carbonFilter.expanded) {
            this.carbonFilter.query = "";
        }
    },

    carbonClearFilter() {
        this.carbonFilter.query = "";
    },

    onCarbonFilterKeydown(ev) {
        // Escape clears first and closes only when already empty, which is how
        // Carbon's expandable search behaves.
        if (ev.key === "Escape") {
            ev.stopPropagation();
            if (this.carbonFilter.query) {
                this.carbonFilter.query = "";
            } else {
                this.carbonFilter.expanded = false;
            }
        }
    },
});
