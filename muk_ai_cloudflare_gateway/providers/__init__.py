from odoo.addons.muk_ai.providers import REGISTRY

from .cloudflare import CloudflareProvider

REGISTRY[CloudflareProvider.name] = CloudflareProvider
