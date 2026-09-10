# Twilio Gateway - SMS Mirror

Bridges Odoo's core SMS pipeline into `mail_gateway_twilio` threads. Every
outbound **core-notification SMS** and **SMS Marketing** message is mirrored into
the recipient's per-contact Twilio gateway channel, so the customer's inbound
replies (captured by the gateway webhook) thread together with the message they
are answering — one unified history in Discuss.

## How it works

- Hooks `sms.sms._handle_call_result_hook` — the single point where **both**
  core notifications and SMS Marketing funnel through after a successful send
  (any provider). Only sent messages are mirrored; errors are ignored.
- The mirror is **display-only**: it posts into the channel with
  `no_gateway_notification=True`, so it never re-sends through Twilio, and it
  never creates a new `sms.sms` — no loops.
- Marketing linkage is read defensively (`mailing_id` only if `mass_mailing_sms`
  is installed), so that module is a soft dependency.

## Choosing the target gateway

Core SMS knows nothing about gateways, and the actual Twilio "From" number is
chosen later (by destination country) and never stored — so we can't route by it.
Resolution (`_resolve_mirror_gateway`, overridable):

1. A per-user gateway whose **webhook user** is the SMS author (notification SMS
   only — supports the per-user-number model).
2. Else the gateway flagged **Mirror outbound SMS here** for the company.
3. Else the only Twilio gateway for the company.

> For replies to actually land in the mirrored thread, the number your company
> sends core/marketing SMS from should be the **same** number backing the target
> gateway; otherwise replies arrive on a different gateway.

## Notes

- Mirrored messages are display copies; delivery status of core SMS stays on the
  core `sms` / `sms.tracker` side.
- The blast text is shown; it is not back-threaded to the campaign record.
