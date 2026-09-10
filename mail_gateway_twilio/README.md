# Mail Twilio Gateway

Two-way **SMS/MMS** for Odoo 18 via [Twilio](https://www.twilio.com), built on the
OCA [`mail_gateway`](https://github.com/OCA/social) framework. Inbound messages
land as a conversation in **Discuss** (one thread per contact); replying in that
thread sends an SMS back. Delivery status is tracked, and inbound picture/media
messages (MMS) arrive as attachments.

## What it does

- **Inbound**: Twilio's webhook posts messages to Odoo → a `discuss.channel`
  (`channel_type="gateway"`) keyed by the sender's phone number. All replies from
  the same number thread into one channel.
- **Outbound**: reply in the Discuss channel, use the **Send SMS** action on a
  contact, or fire the **Twilio SMS** server action from automation.
- **MMS**: inbound media is downloaded (authenticated) and attached; audio is
  flagged as a voice note. *Outbound MMS is not supported* (Twilio requires a
  publicly reachable `MediaUrl`; Odoo attachments are not public).
- **Delivery status**: Twilio `StatusCallback`s update the message's notification
  (delivered → sent, failed/undelivered → exception with the error code).

## Setup

1. Go to **Settings → Technical → Email → Gateway** and create a gateway with
   type **Twilio**.
2. Fill the fields (note the credential mapping shown on the *Twilio
   configuration* tab):
   - **Token** = Twilio **Account SID** (`AC…`).
   - **Webhook Secret** = Twilio **Auth Token** (required — also validates the
     `X-Twilio-Signature` on inbound requests).
   - **Webhook Key** = any random string (secret part of the inbound URL).
   - **Twilio From Number** (E.164) *or* **Messaging Service SID** (`MG…`). If
     both are set, the Messaging Service wins (recommended for US A2P 10DLC).
3. Add the users who should see/answer the conversations under **Members**.
4. Save and press **Integrate Webhook** — the module registers the inbound URL on
   your Twilio number (or Messaging Service) automatically. If that call fails
   (e.g. restricted API key), copy the **Inbound Webhook URL** shown on the form
   into the number's *"A message comes in"* field in the Twilio console.

> **Important:** `web.base.url` must be your public **HTTPS** URL and
> `proxy_mode` must be enabled. Twilio's signature is computed over the exact URL
> it calls, so a mismatch will reject all inbound messages.

## Conversation model

Channels are keyed by `(gateway, phone number)`, so all correspondence with a
contact is one thread. Membership is shared: everyone in the gateway's *Members*
sees every thread — a **team inbox**. For **per-user** private conversations, give
each user their own Twilio number and create one gateway per number with that
user as the sole member (no code needed — pure configuration).

## Related

- `mail_gateway_twilio_sms_mirror` — mirrors outbound **core notification** and
  **SMS Marketing** messages into these same threads, for a unified history.
