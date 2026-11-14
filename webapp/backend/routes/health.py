import time

from flask import Blueprint, jsonify

from .. import extensions as ext

bp = Blueprint("health", __name__)

CHECKS = {
    "elasticsearch": lambda: ext.es.ping(),
    "mongodb": lambda: ext.mongo_client.admin.command("ping")["ok"] == 1.0,
    "redis": lambda: ext.rds.ping(),
}


@bp.route("/")
def home():
    return "Security Monitor - Hello World"


@bp.route("/health")
def health():
    services = {}
    for name, fn in CHECKS.items():
        start = time.perf_counter()
        error = None
        try:
            up = bool(fn())
        except Exception as exc:
            up, error = False, type(exc).__name__
        entry = {"status": "up" if up else "down",
                 "latency_ms": round((time.perf_counter() - start) * 1000, 1)}
        if error:
            entry["error"] = error
        services[name] = entry
    healthy = all(s["status"] == "up" for s in services.values())
    return jsonify(status="healthy" if healthy else "degraded", services=services), \
        (200 if healthy else 503)
