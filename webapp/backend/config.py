import os


class Config:
    ES_HOST = os.environ.get("ES_HOST", "http://elasticsearch:9200")
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb://mongo:27017")
    MONGO_DB = os.environ.get("MONGO_DB", "security_monitor")
    REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
    REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD")
    UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/data")
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", "100")) * 1024 * 1024
    SEARCH_CACHE_TTL = int(os.environ.get("SEARCH_CACHE_TTL", "60"))
    ES_INDEX = "security_logs*"
