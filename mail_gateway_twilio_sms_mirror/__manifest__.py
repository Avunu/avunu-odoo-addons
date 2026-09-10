# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
{
    "name": "Twilio Gateway - SMS Mirror",
    "summary": "Mirror outbound core & marketing SMS into Twilio gateway threads",
    "version": "18.0.1.0.0",
    "category": "Discuss",
    "author": "Avunu LLC",
    "website": "https://avu.nu",
    "license": "AGPL-3",
    "installable": True,
    "depends": [
        "mail_gateway_twilio",
        # Core SMS: both notifications and SMS Marketing funnel through
        # sms.sms._handle_call_result_hook, the single point we mirror from.
        # mass_mailing_sms stays a soft dependency (field-presence checks).
        "sms",
    ],
    "data": [
        "views/mail_gateway.xml",
    ],
}
