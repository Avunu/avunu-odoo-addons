# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import logging

from odoo.http import Controller, request, route

from odoo.addons.mail.models.discuss.mail_guest import add_guest_to_context

_logger = logging.getLogger(__name__)


class TwilioGatewayController(Controller):
    """Twilio-specific inbound webhook.

    The base ``mail_gateway`` controller (``/gateway/<usage>/<token>/update``)
    decodes the request body with ``json.loads``. Twilio instead POSTs
    ``application/x-www-form-urlencoded`` for both inbound messages and status
    callbacks, so we register a more specific route that parses the form data.
    Werkzeug prefers this static ``twilio`` segment over the base route's
    ``<string:usage>`` converter, so it wins for exactly the URL the framework
    generates in ``mail.gateway._get_webhook_url``.
    """

    @route(
        "/gateway/twilio/<string:token>/update",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    @add_guest_to_context
    def twilio_update(self, token, **kwargs):
        bot_data = request.env["mail.gateway"]._get_gateway(
            token, gateway_type="twilio", state="integrated"
        )
        if not bot_data:
            _logger.warning("Twilio gateway not found for webhook_key %s", token)
            return self._twilio_response()
        params = request.httprequest.form.to_dict()
        dispatcher = (
            request.env["mail.gateway.twilio"]
            .with_user(bot_data["webhook_user_id"])
            .with_context(no_gateway_notification=True)
        )
        if not dispatcher._verify_update(bot_data, params):
            _logger.warning(
                "Twilio signature verification failed for webhook_key %s", token
            )
            return self._twilio_response()
        gateway = dispatcher.env["mail.gateway"].browse(bot_data["id"])
        dispatcher._receive_update(gateway, params)
        return self._twilio_response()

    def _twilio_response(self):
        # An empty 200 tells Twilio there is nothing to reply with (no TwiML).
        return request.make_response("", [("Content-Type", "text/plain")])
