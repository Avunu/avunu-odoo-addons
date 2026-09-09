# Copyright 2026 Avunu LLC
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
{
    "name": "Carbon Backend Theme / Company Color",
    "summary": "Drive the Carbon interactive colour from web_company_color",
    "version": "18.0.1.0.0",
    "category": "Themes/Backend",
    "author": "Avunu LLC",
    "website": "https://github.com/Avunu/avunu-odoo-addons",
    "license": "AGPL-3",
    "depends": ["web_theme_carbon", "web_company_color"],
    # Glue module: it exists only to reconcile two modules that are each
    # useful alone, so it installs itself once both are present and is never
    # something anyone has to go looking for.
    "auto_install": True,
    "installable": True,
    # Must load after both parents so the res.company override lands on top of
    # web_company_color's own.
    "sequence": 4,
}
