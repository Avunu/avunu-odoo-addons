# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
{
    "name": "MuK AI - Cloudflare AI Gateway Provider",
    "summary": "Adds Cloudflare Workers AI as a MuK AI provider, routed through "
    "a named Cloudflare AI Gateway for cost tracking.",
    "version": "18.0.1.0.0",
    "category": "Productivity",
    "author": "Avunu LLC",
    "website": "https://avu.nu",
    "license": "AGPL-3",
    "installable": True,
    "depends": [
        "muk_ai",
    ],
    "data": [
        "views/provider_views.xml",
    ],
}
