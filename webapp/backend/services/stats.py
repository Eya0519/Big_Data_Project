import json
import logging
from datetime import datetime, timezone

from .. import extensions as ext
from ..config import Config

log = logging.getLogger(__name__)

CACHE_KEY = "stats:global"
CACHE_TTL = 30          # seconds: the dashboard can poll without hammering Elasticsearch

FAILED_AUTH = {"bool": {"filter": [{"term": {"type_evenement": "authentication"}},
                                   {"term": {"resultat": "echec"}}]}}


def _buckets(agg):
    return [{"key": b["key"], "count": b["doc_count"]} for b in agg.get("buckets", [])]


def compute():
    res = ext.es.search(
        index=Config.ES_INDEX, size=0, track_total_hits=True,
        aggs={
            "today": {"filter": {"range": {"@timestamp": {"gte": "now/d"}}}},
            "high": {"filter": {"term": {"niveau": "eleve"}}},
            "by_level": {"terms": {"field": "niveau", "size": 10}},
            "auth": {"filter": {"term": {"type_evenement": "authentication"}},
                     "aggs": {"by_result": {"terms": {"field": "resultat", "size": 5}}}},
            "failed_auth": {"filter": FAILED_AUTH, "aggs": {
                "top_ips": {"terms": {"field": "ip_source", "size": 10}},
                "by_country": {"terms": {"field": "geoip.country_name", "size": 10}}}},
            "per_day": {"date_histogram": {"field": "@timestamp", "calendar_interval": "day",
                                           "format": "yyyy-MM-dd"}},
        })
    aggs = res.get("aggregations", {})

    def doc_count(name):
        return aggs.get(name, {}).get("doc_count", 0)

    auth_total = doc_count("auth")
    successes = next((b["doc_count"] for b in aggs.get("auth", {}).get("by_result", {}).get("buckets", [])
                      if b["key"] == "succes"), 0)
    failed = aggs.get("failed_auth", {})

    files_by_status = {d["_id"]: d["n"] for d in
                       ext.db.file_metadata.aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}])}

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "totals": {
            "events": res["hits"]["total"]["value"],
            "today": doc_count("today"),
            "high_severity": doc_count("high"),
            "failed_auth": failed.get("doc_count", 0),
        },
        "files": {"total": sum(files_by_status.values()), "by_status": files_by_status},
        "auth_success_rate": round(100 * successes / auth_total, 1) if auth_total else None,
        "by_level": _buckets(aggs.get("by_level", {})),
        "top_failed_ips": _buckets(failed.get("top_ips", {})),
        "failed_auth_by_country": _buckets(failed.get("by_country", {})),
        "events_per_day": [{"date": b["key_as_string"], "count": b["doc_count"]}
                           for b in aggs.get("per_day", {}).get("buckets", [])],
    }


def get_stats():
    try:
        cached = ext.rds.get(CACHE_KEY)
        if cached:
            data = json.loads(cached)
            data["cached"] = True
            return data
    except Exception as exc:
        log.warning("stats cache read failed: %s", type(exc).__name__)

    data = compute()
    try:
        ext.rds.setex(CACHE_KEY, CACHE_TTL, json.dumps(data))
    except Exception as exc:
        log.warning("stats cache write failed: %s", type(exc).__name__)
    data["cached"] = False
    return data
