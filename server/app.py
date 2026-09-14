import logging
import os
import sqlite3
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify
from waitress import serve
from server import db_session
from server.config import CONFIG_PATH, HOST, PORT, USER_TOKENS, write_template
from server.payload import BadRequest
from server.routes.system import system_bp
from server.routes.catalog import catalog_bp
from server.routes.chores import chores_bp
from server.routes.plans import plans_bp
from server.routes.logs import logs_bp
from server.routes.pomodoro import pomodoro_bp
from server.routes.records import records_bp

log = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__)
    db_session.init_app(app)

    @app.errorhandler(sqlite3.IntegrityError)
    def constraint_violated(error):
        """Answer a CHECK or foreign key the store refused."""
        return jsonify({"error": str(error)}), 400

    @app.errorhandler(BadRequest)
    def request_refused(error):
        """Answer a request the service cannot honour."""
        return jsonify({"error": str(error)}), 400

    @app.errorhandler(sqlite3.Error)
    def store_failed(error):
        """Answer a store failure that is not a constraint violation."""
        log.exception("The store could not complete a request: %s", error)
        return jsonify({"error": "The household store could not complete that request."}), 500

    app.register_blueprint(system_bp, url_prefix="/api")
    app.register_blueprint(catalog_bp, url_prefix="/api/catalog")
    app.register_blueprint(chores_bp, url_prefix="/api/chores")
    app.register_blueprint(plans_bp, url_prefix="/api/plans")
    app.register_blueprint(logs_bp, url_prefix="/api/logs")
    app.register_blueprint(records_bp, url_prefix="/api/logs")
    app.register_blueprint(pomodoro_bp, url_prefix="/api/pomodoro")
    return app

if __name__ == "__main__":
    from src.logging_setup import configure as configure_logging

    configure_logging()

    if not USER_TOKENS:
        write_template(CONFIG_PATH)
        log.error("No members are configured. Name each one under [[members]] in %s and "
                  "start again; a member left without a token is given one.", CONFIG_PATH)
        sys.exit(1)

    app = create_app()
    log.info("Starting the Traker API server on http://%s:%s for %s", HOST, PORT,
             ", ".join(sorted(USER_TOKENS.values())))
    serve(app, host=HOST, port=PORT, threads=16)
