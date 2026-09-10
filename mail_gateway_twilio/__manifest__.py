# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
{
    "name": "Mail Twilio Gateway",
    "summary": "Two-way SMS/MMS gateway for Twilio, threaded into Discuss",
    "version": "18.0.1.0.0",
    "category": "Discuss",
    "author": "Avunu LLC",
    "website": "https://avu.nu",
    "license": "AGPL-3",
    "installable": True,
    "depends": [
        "mail_gateway",
        # phone_validation provides mail.thread.phone / _phone_format /
        # res.partner.phone_sanitized used to match inbound numbers to partners.
        "phone_validation",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizards/twilio_composer.xml",
        "views/mail_gateway.xml",
    ],
}
