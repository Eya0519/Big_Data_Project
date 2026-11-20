import logging
import re

from flask import Blueprint, jsonify, request

from ..services import logs as logs_svc
from ..services import search as search_svc
from ..services import stats as stats_svc

log = logging.getLogger(__name__)
bp = Blueprint("api", __name__, url_prefix="/api/v1")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
UNAVAILABLE = "Service momentanément indisponible."


@bp.route("/logs")
def list_logs():
    try:
        params = search_svc.parse_params(request.args)
    except search_svc.SearchError as exc:
        return jsonify(error=str(exc)), 400
    try:
        return jsonify(search_svc.search(params))
    except Exception:
        log.exception("log listing failed")
        return jsonify(error=UNAVAILABLE), 503


@bp.route("/logs/<log_id>")
def get_log(log_id):
    if not ID_RE.match(log_id):
        return jsonify(error="Identifiant invalide."), 400
    try:
        doc = logs_svc.get_log(log_id)
    except Exception:
        log.exception("log lookup failed")
        return jsonify(error=UNAVAILABLE), 503
    if doc is None:
        return jsonify(error="Événement introuvable."), 404
    return jsonify(doc)


@bp.route("/stats")
def stats():
    try:
        return jsonify(stats_svc.get_stats())
    except Exception:
        log.exception("stats failed")
        return jsonify(error=UNAVAILABLE), 503
