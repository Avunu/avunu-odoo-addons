# Avunu Odoo addons

Odoo 18 modules built and maintained by [Avunu LLC](https://avunu.net) for our own client work, published for anyone to use. The collection covers email and SMS transports, a pipeline that turns emailed or printed documents into Odoo records, an AI provider, and a handful of backend and shop floor improvements.

This is the `18.0` branch. Every module here targets Odoo 18.0 Community (or [OCB](https://github.com/OCA/OCB)) and builds on [OCA](https://odoo-community.org/) modules where one exists rather than duplicating it.

## Modules

### Email and messaging

| Module | What it does | License |
| --- | --- | --- |
| [`mail_cloudflare`](mail_cloudflare/README.md) | Sends mail through the Cloudflare Email Sending API and receives it from the Cloudflare email relay over a signed webhook; no SMTP or IMAP provider in the loop | AGPL-3.0-or-later |
| [`mail_gateway_twilio`](mail_gateway_twilio/README.md) | Two-way SMS/MMS through Twilio, one Discuss thread per contact, built on the OCA `mail_gateway` framework | AGPL-3.0-or-later |
| [`mail_gateway_twilio_sms_mirror`](mail_gateway_twilio_sms_mirror/README.md) | Mirrors Odoo's outbound core and marketing SMS into the matching Twilio gateway threads so replies sit next to what they answer | AGPL-3.0-or-later |

### Document import pipeline

These modules extend the OCA `base_import_pdf_by_template` so that a PDF, an email body or a printed document can be turned into an Odoo record by a template of patterns, with a live preview while you write them.

| Module | What it does | License |
| --- | --- | --- |
| [`base_import_pdf_by_template_engine`](base_import_pdf_by_template_engine/README.md) | Two small extension points on the base module so other pattern engines and tooling can plug in without copying its methods; also fixes two table-extraction bugs | AGPL-3.0-or-later |
| [`import_preview`](import_preview/README.md) | A persistent sample document per template and a live preview of what each line's pattern matches, right in the line dialog | AGPL-3.0-or-later |
| [`import_via_xberg`](import_via_xberg/README.md) | An `xberg` extraction mode for structured (JSON) document parsing, plus optional JSONPath narrowing on template lines | AGPL-3.0-or-later |
| [`import_create_missing`](import_create_missing/README.md) | Creates the linked document on the fly when a line's search finds nothing, filled from fixed values or from the same pattern matching the line uses | AGPL-3.0-or-later |
| [`import_create_missing_xberg`](import_create_missing_xberg/README.md) | JSONPath narrowing for `import_create_missing` values on `xberg` templates; installs itself when both of its dependencies are present | AGPL-3.0-or-later |
| [`import_from_email`](import_from_email/README.md) | Plain text and HTML extraction modes, a `mail.alias` entry point onto `edi.exchange.record`, and a generic template-driven EDI input processor | AGPL-3.0-or-later |
| [`edi_import_router`](edi_import_router/README.md) | One inbox for emailed and printed documents: TypeSafe picks the EDI exchange type, and so the import template, for each one | AGPL-3.0-or-later |

### AI

| Module | What it does | License |
| --- | --- | --- |
| [`muk_ai_cloudflare_gateway`](muk_ai_cloudflare_gateway/README.md) | Adds Cloudflare Workers AI as a MuK AI provider, optionally routed through a named Cloudflare AI Gateway for usage tracking | AGPL-3.0-or-later |

### UI and shop floor

| Module | What it does | License |
| --- | --- | --- |
| [`web_theme_carbon`](web_theme_carbon/README.md) | IBM Carbon Design System theme for the Odoo backend, light (g10) and dark (g100), with per-company brand colours | AGPL-3.0-or-later |
| [`hr_timesheet_time_control_systray`](hr_timesheet_time_control_systray/README.md) | Shows the running timesheet timer, ticking, in the systray, with a stop button that works from any screen | AGPL-3.0-or-later |
| [`shopfloor_mobile_base_auth_oauth`](shopfloor_mobile_base_auth_oauth/README.md) | Google and Apple sign-in for OCA Shopfloor mobile apps, in place of typing an API key by hand | AGPL-3.0-or-later |
| [`shopfloor_mobile_camera_scan`](shopfloor_mobile_camera_scan/README.md) | Device-camera barcode scanning for the Shopfloor mobile app, delivered through the same code path as a hardware scanner | LGPL-3.0-or-later |

## Install

Requires Odoo 18.0 and a PostgreSQL database. Pick the module or modules you want; each pulls in the modules it depends on (see below), and those must be on your `addons_path` first.

With a plain Odoo checkout, clone this repository on its `18.0` branch and add it to the addons path:

```sh
git clone --branch 18.0 https://github.com/Avunu/avunu-odoo-addons.git
odoo-bin --addons-path=odoo/addons,/path/to/avunu-odoo-addons,<your other addons paths> \
  -d <database> -i <module> --stop-after-init
```

With [odoo-nix](https://github.com/Avunu/odoo-nix), add the repository from the dev shell. `odoo module add` accepts an `owner/repo` and a branch, adds it as a submodule, and the addons path is regenerated from the folders present (run `direnv reload` afterwards):

```sh
odoo module add Avunu/avunu-odoo-addons 18.0
```

## Dependencies

Each module's `__manifest__.py` is the source of truth. Besides Odoo core modules (`mail`, `bus`, `sms`, `phone_validation`, `web`), the modules depend on the following. The OCA repositories listed are the 18.0 branches; clone the ones your chosen modules need.

| Module | Needs from OCA or others | Python packages |
| --- | --- | --- |
| `mail_cloudflare` | none beyond core | none |
| `mail_gateway_twilio` | `mail_gateway` ([OCA/social](https://github.com/OCA/social)) | none |
| `mail_gateway_twilio_sms_mirror` | `mail_gateway_twilio` (this repository) | none |
| `base_import_pdf_by_template_engine` | `base_import_pdf_by_template` ([OCA/edi](https://github.com/OCA/edi)) | none |
| `import_preview` | `base_import_pdf_by_template_engine` (this repository) | none |
| `import_via_xberg` | `base_import_pdf_by_template_engine` (this repository) | `jsonpath_ng`, `xberg` |
| `import_create_missing` | `base_import_pdf_by_template_engine` (this repository) | none |
| `import_create_missing_xberg` | `import_create_missing` and `import_via_xberg` (this repository) | none |
| `import_from_email` | `base_import_pdf_by_template` ([OCA/edi](https://github.com/OCA/edi)), `edi_core_oca` ([OCA/edi-framework](https://github.com/OCA/edi-framework)), `base_import_pdf_by_template_engine` (this repository) | none |
| `edi_import_router` | `queue_job` ([OCA/queue](https://github.com/OCA/queue)), `import_from_email` (this repository) | `typesafe_sdk`, `pypdf` |
| `muk_ai_cloudflare_gateway` | `muk_ai` ([muk-it/odoo-modules](https://github.com/muk-it/odoo-modules)) | none |
| `web_theme_carbon` | `web_responsive` and `web_dark_mode` ([OCA/web](https://github.com/OCA/web)) | none |
| `hr_timesheet_time_control_systray` | `project_timesheet_time_control` ([OCA/project](https://github.com/OCA/project)) | none |
| `shopfloor_mobile_base_auth_oauth` | `shopfloor_mobile_base` and `shopfloor_mobile_base_auth_api_key` ([OCA/shopfloor-app](https://github.com/OCA/shopfloor-app)), `auth_oidc` ([OCA/server-auth](https://github.com/OCA/server-auth)), `server_environment` ([OCA/server-env](https://github.com/OCA/server-env)) | none |
| `shopfloor_mobile_camera_scan` | `shopfloor_mobile_base` ([OCA/shopfloor-app](https://github.com/OCA/shopfloor-app)) | none |

`web_theme_carbon` also has a build-time npm toolchain for regenerating its Carbon tokens; it is not needed to run the theme. See its README.

## Tests

Odoo runs a module's tests when you install or update it with `--test-enable`. Select a module's tests with a `--test-tags` filter and use a throwaway database:

```sh
odoo-bin -c odoo.conf -d <testdb> -i <module> \
  --test-enable --test-tags /<module> --stop-after-init
```

Notes from the module READMEs:

- `mail_cloudflare` tests need the dev mail catcher off in an odoo-nix shell: prefix the command with `ODOO_MAILCATCH_ENABLED=0`.
- `web_theme_carbon` runs its cascade tests with `odoo -u web_theme_carbon --test-enable --stop-after-init`, and checks that its generated assets are current with `npm run check` in the module directory.
- `hr_timesheet_time_control_systray` includes a browser tour that runs after install.
- `shopfloor_mobile_base_auth_oauth` and `shopfloor_mobile_camera_scan` have no automated tests.

## Part of the Cloudflare Email suite

Four open-source projects work together to give business systems email without SMTP credentials or IMAP polling:

| Project | Role |
|---|---|
| [cloudflare-email-relay](https://github.com/Avunu/cloudflare-email-relay) | Multi-tenant inbound Worker: stores each message in R2, then delivers it to the right system with signed, retried requests |
| [cloudflare_email_delivery](https://github.com/Avunu/cloudflare_email_delivery) | Frappe and ERPNext adapter |
| [mail_cloudflare](https://github.com/Avunu/avunu-odoo-addons/tree/18.0/mail_cloudflare) | Odoo adapter |
| [wordpress-cloudflare-email](https://github.com/Avunu/wordpress-cloudflare-email) | WordPress plugin: outbound mail and a delivery log |

Need it set up for your business? [Avunu](https://avunu.net) can help.

## License

Every module is licensed under the [GNU Affero General Public License v3.0 or later](LICENSE), except `shopfloor_mobile_camera_scan`, which is licensed under the [GNU Lesser General Public License v3.0 or later](LICENSES/LGPL-3.0-or-later.txt). The licence of each module is also stated in its `__manifest__.py` (`AGPL-3` or `LGPL-3`, Odoo's identifiers for version 3) and in its source file headers.

Some modules vendor third-party code that keeps its own licence: `html5-qrcode` (Apache-2.0) in `shopfloor_mobile_camera_scan`, `microlighter` (MIT) in `import_preview`, and the IBM Plex fonts (SIL Open Font License 1.1) in `web_theme_carbon`. Their licence texts sit next to the vendored files.

## Contributing

Issues and pull requests are welcome. Each module's README explains why it exists and how it works.
