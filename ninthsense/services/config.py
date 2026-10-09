"""The only reader of the addon's `ir.config_parameter` keys."""

from odoo.modules.module import current_test
from odoo.tools import config as odoo_config

from ..core import config as core_config

PORTAL_URL_KEY = "ninthsense.portal_url"
SECRET_KEY = "ninthsense.secret"
LINK_VALIDITY_DAYS_KEY = "ninthsense.link_validity_days"
_KEY_PREFIX = "ninthsense."


def _allow_insecure_localhost() -> bool:
    """Plain http to localhost is for tests and developer machines, never production."""
    return bool(odoo_config["test_enable"] or current_test or odoo_config["dev_mode"])


def parse(portal_url, secret, link_validity_days) -> core_config.Config:
    """Parse raw settings the way `load` does, for values that are not stored yet."""
    return core_config.parse(
        portal_url,
        secret,
        link_validity_days,
        allow_insecure_localhost=_allow_insecure_localhost(),
    )


def load(env) -> core_config.Config:
    """The current settings, parsed. Missing values are reported by `require_ready()`."""
    params = env["ir.config_parameter"].sudo()
    return parse(
        params.get_str(PORTAL_URL_KEY, None),
        params.get_str(SECRET_KEY, None),
        params.get_str(LINK_VALIDITY_DAYS_KEY, None),
    )


def delete_all(env):
    """Delete every `ir.config_parameter` key the addon owns, stored or not."""
    params = env["ir.config_parameter"].sudo()
    # `_` is a LIKE wildcard, so the prefix is checked again exactly.
    params.search([("key", "=like", f"{_KEY_PREFIX}%")]).filtered(
        lambda param: param.key.startswith(_KEY_PREFIX)
    ).unlink()
