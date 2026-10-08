from . import controllers, models, services, wizard


def post_load():
    """Keep link tokens out of Odoo's access log, for every database this server runs."""
    from .core import log

    log.install_token_filter()


def uninstall_hook(env):
    """Remove the addon's settings, the wrapper secret among them."""
    from .services import config

    config.delete_all(env)
