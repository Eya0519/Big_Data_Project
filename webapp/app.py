import os
import redis
from elasticsearch import Elasticsearch
from flask import Flask, jsonify
from pymongo import MongoClient

app = Flask(__name__)


def check_es():
    return Elasticsearch(os.environ["ES_HOST"]).ping()


def check_mongo():
    c = MongoClient(os.environ["MONGO_URI"], serverSelectionTimeoutMS=2000)
    return c.admin.command("ping")["ok"] == 1.0


def check_redis():
    r = redis.Redis(host=os.environ["REDIS_HOST"], password=os.environ["REDIS_PASSWORD"],
                    socket_connect_timeout=2)
    return r.ping()


@app.route("/")
def home():
    return "Security Monitor - Hello World"


@app.route("/health")
def health():
    status = {}
    for name, fn in [("elasticsearch", check_es), ("mongodb", check_mongo), ("redis", check_redis)]:
        try:
            status[name] = "up" if fn() else "down"
        except Exception as e:
            status[name] = f"down ({type(e).__name__})"
    ok = all(v == "up" for v in status.values())
    return jsonify(status=("healthy" if ok else "degraded"), services=status), (200 if ok else 503)
