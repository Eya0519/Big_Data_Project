import logging
from datetime import datetime, timezone

from .. import extensions as ext

log = logging.getLogger(__name__)

FINAL = {"indexed", "partial", "failed"}
TIMEOUT_SECONDS = 120


def _count(index, field, name):
    res = ext.es.count(index=index, query={"term": {field: name}}, ignore_unavailable=True)
    return res["count"]


def refresh(doc):
    """Compare what Elasticsearch holds for this file with what was expected."""
    if doc["status"] in FINAL:
        return doc
    try:
        indexed = _count("security_logs*", "source_file", doc["stored_name"])
        errors = _count("logs_parse_errors", "source_file.keyword", doc["stored_name"])
    except Exception as exc:
        log.warning("status refresh failed: %s", type(exc).__name__)
        return doc

    done = indexed + errors
    if done >= doc["rows_expected"]:
        status = "indexed" if errors == 0 else "partial"
    else:
        age = (datetime.now(timezone.utc)
               - doc["uploaded_at"].replace(tzinfo=timezone.utc)).total_seconds()
        if age > TIMEOUT_SECONDS:
            status = "partial" if done else "failed"
        else:
            status = "processing" if done else "pending"

    update = {"status": status, "rows_indexed": indexed, "rows_errors": errors}
    if any(doc.get(k) != v for k, v in update.items()):
        ext.db.file_metadata.update_one({"_id": doc["_id"]}, {"$set": update})
        doc.update(update)
    return doc


def serialize(doc):
    out = dict(doc)
    out["id"] = str(out.pop("_id"))
    out["uploaded_at"] = out["uploaded_at"].isoformat() + "Z"
    return out
