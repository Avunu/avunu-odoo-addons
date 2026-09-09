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
 * SCOPE. Filtering only what is on screen is close to useless where this is most
 * needed: an ir.model form lists hundreds of fields, forty at a time, and a
 * search that cannot see past the current page will not find the field you want.
 *
 * So for a RELATIONAL list -- an x2many inside a form -- the whole relation is
 * pulled in before filtering. That is bounded and cheap: the ids are already
 * known client-side, it happens once per search, and the original pagination is
 * restored when the query is cleared. It is capped (CARBON_MAX_EXPAND) so a
 * pathologically large relation is left alone rather than dragged into the
 * browser.
 *
 * A VIEW list is different: its record set is a server-side domain that could be
 * millions of rows, so nothing is pre-loaded and the filter stays on the loaded
 * page. Either way the toolbar shows "n of m" while a query is active, because
 * the difference matters and should not have to be inferred.
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

/**
 * Above this many records, a relational list is left paginated rather than
 * pulled in whole. Field lists -- the case this exists for -- are in the
 * hundreds; anything past a few thousand is a different problem and should not
 * be silently loaded into the browser because someone typed a letter.
 */
const CARBON_MAX_EXPAND = 2000;

patch(ListRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        this.carbonFilter = useState({ query: "", expanded: false, loading: false });
        // Pagination to restore when the query is cleared.
        this._carbonPageRestore = null;
    },

    /**
     * True for an x2many list, whose record set is a known, bounded list of ids.
     *
     * Duck-typed on `resIds`, which is a getter on StaticList and absent on the
     * dynamic (view) lists. Checking the class name would not survive
     * minification, and `_parent` is private.
     */
    get carbonIsRelational() {
        return Array.isArray(this.props.list.resIds);
    },

    /**
     * Pull in the rest of a relational list so the filter can see all of it.
     *
     * Without this the search on an ir.model's Fields tab only ever looks at
     * the forty rows on screen, which is precisely the case it is for.
     */
    async carbonEnsureFullyLoaded() {
        const list = this.props.list;
        if (!this.carbonIsRelational || this._carbonPageRestore) {
            return;
        }
        if (list.count <= list.records.length || list.count > CARBON_MAX_EXPAND) {
            return;
        }
        this._carbonPageRestore = { limit: list.limit, offset: list.offset };
        this.carbonFilter.loading = true;
        try {
            await list.load({ limit: list.count, offset: 0 });
        } finally {
            this.carbonFilter.loading = false;
        }
        this.render(true);
    },

    /** Put the pager back the way it was. */
    async carbonRestorePage() {
        const restore = this._carbonPageRestore;
        if (!restore) {
            return;
        }
        this._carbonPageRestore = null;
        await this.props.list.load(restore);
        this.render(true);
    },

    async onCarbonFilterInput(ev) {
        this.carbonFilter.query = ev.target.value;
        if (this.carbonFilter.query) {
            await this.carbonEnsureFullyLoaded();
        } else {
            await this.carbonRestorePage();
        }
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
        // Once a relational list has been pulled in whole, records.length IS
        // the relation, so "n of m" reads against everything the user expects
        // rather than against a page they can no longer see.
        return { shown, total: records.length };
    },

    get carbonFilterPlaceholder() {
        return _t("Search this page");
    },

    get carbonFilterLabel() {
        return _t("Search the rows on this page");
    },

    async carbonToggleFilter() {
        this.carbonFilter.expanded = !this.carbonFilter.expanded;
        if (!this.carbonFilter.expanded) {
            this.carbonFilter.query = "";
            await this.carbonRestorePage();
        }
    },

    async carbonClearFilter() {
        this.carbonFilter.query = "";
        await this.carbonRestorePage();
    },

    onCarbonFilterKeydown(ev) {
        // Escape clears first and closes only when already empty, which is how
        // Carbon's expandable search behaves.
        if (ev.key === "Escape") {
            ev.stopPropagation();
            if (this.carbonFilter.query) {
                this.carbonFilter.query = "";
                this.carbonRestorePage();
            } else {
                this.carbonFilter.expanded = false;
            }
        }
    },
});
