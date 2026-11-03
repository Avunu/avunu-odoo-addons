# Avunu Odoo addons (moved)

This repository is retired. In November 2026 its modules moved, with their history, to one repository per [OCA](https://odoo-community.org/) area, following the way the OCA organizes its own addons. The last commit that still holds the modules here is [`301b645`](https://github.com/Avunu/avunu-odoo-addons/tree/301b6452851c68c56725063b818d0995afab54ad).

| Module | Now in |
| --- | --- |
| `mail_cloudflare`, `mail_gateway_twilio`, `mail_gateway_twilio_sms_mirror` | [Avunu/mail-addons](https://github.com/Avunu/mail-addons) |
| `base_import_pdf_by_template_engine`, `import_preview`, `import_via_xberg`, `import_create_missing`, `import_create_missing_xberg`, `import_from_email`, `edi_import_router` | [Avunu/edi-addons](https://github.com/Avunu/edi-addons) |
| `auto_backup_fs_storage` | [Avunu/server-tools-addons](https://github.com/Avunu/server-tools-addons) |
| `muk_ai_cloudflare_gateway` | [Avunu/ai-addons](https://github.com/Avunu/ai-addons) |
| `web_theme_carbon` | [Avunu/web-addons](https://github.com/Avunu/web-addons) |
| `hr_timesheet_time_control_systray` | [Avunu/timesheet-addons](https://github.com/Avunu/timesheet-addons) |
| `shopfloor_mobile_base_auth_oauth`, `shopfloor_mobile_camera_scan` | [Avunu/shopfloor-app-addons](https://github.com/Avunu/shopfloor-app-addons) |

Each new repository has two branches: `develop`, where pull requests go, and `18.0`, which follows `develop` and is the branch to install. With [odoo-nix](https://github.com/Avunu/odoo-nix):

```sh
odoo module add Avunu/mail-addons 18.0
```

The module names are unchanged, so a database that has them installed needs no migration: put the new repository on the addons path in place of this one and update as usual.
