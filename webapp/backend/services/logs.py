from .. import extensions as ext
from ..config import Config


def get_log(log_id):
    """Find one event by its Elasticsearch id, across all monthly indices."""
    res = ext.es.search(index=Config.ES_INDEX, query={"ids": {"values": [log_id]}}, size=1)
    hits = res["hits"]["hits"]
    if not hits:
        return None
    hit = hits[0]
    return {"id": hit["_id"], "index": hit["_index"], "event": hit["_source"]}
