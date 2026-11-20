import logging

from flask import Flask, jsonify
from werkzeug.exceptions import RequestEntityTooLarge

from . import extensions
from .config import Config
from .routes import api, health, search, upload


def create_app():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = Flask(__name__)
    app.config.from_object(Config)
    extensions.init_clients(app.config)
    extensions.ping_all()

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_):
        limit = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
        return jsonify(error=f"Fichier trop volumineux (limite : {limit} Mo)."), 413

    app.register_blueprint(health.bp)
    app.register_blueprint(upload.bp)
    app.register_blueprint(search.bp)
    app.register_blueprint(api.bp)
    return app
