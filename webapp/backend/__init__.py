import logging

from flask import Flask

from . import extensions
from .config import Config
from .routes import health


def create_app():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = Flask(__name__)
    app.config.from_object(Config)
    extensions.init_clients(app.config)
    extensions.ping_all()
    app.register_blueprint(health.bp)
    return app
