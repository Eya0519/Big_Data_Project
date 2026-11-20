import logging

from flask import Blueprint, jsonify, request

from .. import extensions as ext
from ..services import search as svc

log = logging.getLogger(__name__)
bp = Blueprint("search", __name__)


@bp.route("/search")
def search_logs():
    try:
        params = svc.parse_params(request.args)
    except svc.SearchError as exc:
        return jsonify(error=str(exc)), 400
    try:
        data = svc.search(params)
    except Exception:
        log.exception("search failed")
        return jsonify(error="Recherche momentanément indisponible."), 503
    if params["page"] == 1:                 # one history entry per search, not per page turned
        svc.record_history(params, data)
    return jsonify(data)


@bp.route("/api/v1/searches")
def search_history():
    docs = ext.db.search_history.find().sort("searched_at", -1).limit(20)
    return jsonify(searches=[{
        "id": str(d["_id"]), "params": d["params"], "total": d["total"],
        "searched_at": d["searched_at"].isoformat() + "Z"} for d in docs])
