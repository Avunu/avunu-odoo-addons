# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
{
    "name": "Cloudflare Email Transport",
    "summary": "Send and receive email via Cloudflare Email Sending and Email Routing",
    "version": "18.0.1.2.0",
    "category": "Discuss",
    "author": "Avunu LLC",
    "website": "https://avu.nu",
    "license": "AGPL-3",
    "installable": True,
    "depends": ["mail"],
    "data": [
        "views/ir_mail_server_views.xml",
        "views/fetchmail_server_views.xml",
    ],
}
