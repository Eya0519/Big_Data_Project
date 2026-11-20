import hashlib
import ipaddress
import json
import logging
import math
from datetime import datetime, timezone

from pymongo.errors import PyMongoError

from .. import extensions as ext
from ..config import Config

log = logging.getLogger(__name__)

MAX_SIZE = 100
MAX_WINDOW = 10000          # Elasticsearch default limit on page * size

SORTABLE = {                # public name -> (field, type used if the field is unmapped)
    "timestamp": ("@timestamp", "date"),
    "ip": ("ip_source", "ip"),
    "user": ("utilisateur", "keyword"),
    "type": ("type_evenement", "keyword"),
    "result": ("resultat", "keyword"),
    "level": ("niveau", "keyword"),
    "service": ("service", "keyword"),
}
EXACT_FILTERS = {"user": "utilisateur", "type": "type_evenement", "result": "resultat",
                 "level": "niveau", "service": "service"}
TEXT_FIELDS = ["description", "utilisateur", "ressource", "service", "type_evenement"]
SOURCE_FIELDS = ["@timestamp", "ip_source", "utilisateur", "type_evenement", "resultat",
                 "niveau", "ressource", "service", "description", "geoip.country_name",
                 "source_file"]


class SearchError(ValueError):
    """Invalid search parameters (answered with HTTP 400)."""


def _parse_date(value, end_of_day=False):
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise SearchError(f"Date invalide : {value!r} (format AAAA-MM-JJ ou ISO 8601).")
    if end_of_day and len(value) == 10:
        return value + "T23:59:59.999"
    return value


def parse_params(args):
    p = {}
    q = (args.get("q") or "").strip()
    if q:
        p["q"] = q
    for name in EXACT_FILTERS:
        value = (args.get(name) or "").strip()
        if value:
            p[name] = value

    ip = (args.get("ip") or "").strip()
    if ip:
        try:
            ipaddress.ip_network(ip, strict=False)
        except ValueError:
            raise SearchError(f"Adresse IP ou plage CIDR invalide : {ip!r}.")
        p["ip"] = ip

    if (args.get("from") or "").strip():
        p["from"] = _parse_date(args["from"].strip())
    if (args.get("to") or "").strip():
        p["to"] = _parse_date(args["to"].strip(), end_of_day=True)

    try:
        page = int(args.get("page", 1))
        size = int(args.get("size", 50))
    except ValueError:
        raise SearchError("Les paramètres « page » et « size » doivent être des entiers.")
    if page < 1 or not 1 <= size <= MAX_SIZE:
        raise SearchError(f"« page » doit être au moins 1 et « size » entre 1 et {MAX_SIZE}.")
    if page * size > MAX_WINDOW:
        raise SearchError(f"Seuls les {MAX_WINDOW} premiers résultats sont accessibles : "
                          "affinez la recherche avec des filtres.")

    sort = args.get("sort", "timestamp")
    order = args.get("order", "desc")
    if sort not in SORTABLE:
        raise SearchError("Tri impossible, valeurs acceptées : " + ", ".join(SORTABLE) + ".")
    if order not in ("asc", "desc"):
        raise SearchError("« order » doit valoir asc ou desc.")

    p.update(page=page, size=size, sort=sort, order=order)
    return p


def build_query(p):
    must, filters = [], []
    if "q" in p:
        must.append({"simple_query_string": {"query": p["q"], "fields": TEXT_FIELDS,
                                             "default_operator": "and"}})
    for name, field in EXACT_FILTERS.items():
        if name in p:
            filters.append({"term": {field: p[name]}})
    if "ip" in p:
        filters.append({"term": {"ip_source": p["ip"]}})
    period = {}
    if "from" in p:
        period["gte"] = p["from"]
    if "to" in p:
        period["lte"] = p["to"]
    if period:
        filters.append({"range": {"@timestamp": period}})
    if not must and not filters:
        return {"match_all": {}}
    return {"bool": {"must": must, "filter": filters}}


def _format_hit(hit):
    s = hit["_source"]
    return {
        "id": hit["_id"],
        "timestamp": s.get("@timestamp"),
        "ip_source": s.get("ip_source"),
        "utilisateur": s.get("utilisateur"),
        "type_evenement": s.get("type_evenement"),
        "resultat": s.get("resultat"),
        "niveau": s.get("niveau"),
        "ressource": s.get("ressource"),
        "service": s.get("service"),
        "description": s.get("description"),
        "pays": (s.get("geoip") or {}).get("country_name"),
        "source_file": s.get("source_file"),
    }


def run_search(p):
    field, unmapped = SORTABLE[p["sort"]]
    sort = [{field: {"order": p["order"], "unmapped_type": unmapped}}]
    if field != "@timestamp":
        sort.append({"@timestamp": {"order": "desc", "unmapped_type": "date"}})

    res = ext.es.search(index=Config.ES_INDEX, query=build_query(p), sort=sort,
                        from_=(p["page"] - 1) * p["size"], size=p["size"],
                        source_includes=SOURCE_FIELDS, track_total_hits=True)
    total = res["hits"]["total"]["value"]
    return {"total": total, "page": p["page"], "size": p["size"],
            "pages": math.ceil(total / p["size"]), "took_ms": res["took"],
            "results": [_format_hit(h) for h in res["hits"]["hits"]]}


def _cache_key(p):
    raw = json.dumps(p, sort_keys=True, ensure_ascii=False)
    return "search:" + hashlib.sha256(raw.encode()).hexdigest()


def search(p):
    """Redis first; on a miss, query Elasticsearch and cache the answer with a TTL."""
    key = _cache_key(p)
    try:
        cached = ext.rds.get(key)
        if cached:
            data = json.loads(cached)
            data["cached"] = True
            return data
    except Exception as exc:
        log.warning("cache read failed: %s", type(exc).__name__)

    data = run_search(p)
    try:
        ext.rds.setex(key, Config.SEARCH_CACHE_TTL, json.dumps(data))
    except Exception as exc:
        log.warning("cache write failed: %s", type(exc).__name__)
    data["cached"] = False
    return data


def record_history(p, data):
    try:
        ext.db.search_history.insert_one({
            "params": p, "total": data["total"], "cached": data["cached"],
            "searched_at": datetime.now(timezone.utc)})
    except PyMongoError as exc:
        log.warning("history not saved: %s", type(exc).__name__)
