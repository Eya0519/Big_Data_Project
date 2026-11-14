import logging

import redis
from elasticsearch import Elasticsearch
from pymongo import MongoClient

log = logging.getLogger(__name__)

es = None
mongo_client = None
db = None
rds = None


def init_clients(cfg):
    global es, mongo_client, db, rds
    es = Elasticsearch(cfg["ES_HOST"], request_timeout=10)
    mongo_client = MongoClient(cfg["MONGO_URI"], serverSelectionTimeoutMS=3000)
    db = mongo_client[cfg["MONGO_DB"]]
    rds = redis.Redis(host=cfg["REDIS_HOST"], password=cfg["REDIS_PASSWORD"],
                      decode_responses=True, socket_connect_timeout=2)


def ping_all():
    """Startup connectivity test: logs the result and never crashes the app."""
    checks = {
        "elasticsearch": lambda: es.ping(),
        "mongodb": lambda: mongo_client.admin.command("ping")["ok"] == 1.0,
        "redis": lambda: rds.ping(),
    }
    for name, fn in checks.items():
        try:
            ok = fn()
        except Exception as exc:
            log.warning("%s unreachable at startup: %s", name, type(exc).__name__)
        else:
            log.info("%s connection %s", name, "OK" if ok else "FAILED")
