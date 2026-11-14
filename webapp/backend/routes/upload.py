import logging
import os
import uuid
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, current_app, jsonify, request
from pymongo.errors import PyMongoError
from werkzeug.utils import secure_filename

from .. import extensions as ext
from ..services import ingestion, validation

log = logging.getLogger(__name__)
bp = Blueprint("upload", __name__)
ALLOWED = {".csv": "csv", ".json": "json"}


def _error(message, status=400, details=None):
    body = {"error": message}
    if details:
        body["details"] = details
    return jsonify(body), status


@bp.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if file is None or not file.filename:
        return _error("Aucun fichier reçu (champ « file » attendu).")

    original = file.filename
    stem, suffix = os.path.splitext(original)
    fmt = ALLOWED.get(suffix.lower())
    if fmt is None:
        return _error("Extension non supportée. Formats acceptés : .csv, .json.", 415)

    raw = file.read()
    try:
        result = validation.validate(fmt, raw)
    except validation.ValidationError as exc:
        return _error(exc.message, 422, exc.details)

    now = datetime.now(timezone.utc)
    stored = f"{now:%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:6]}_{secure_filename(stem) or 'logs'}.{fmt}"
    base = current_app.config["UPLOAD_DIR"]
    tmp_dir, target_dir = os.path.join(base, ".tmp"), os.path.join(base, fmt)
    os.makedirs(tmp_dir, exist_ok=True)
    os.makedirs(target_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, stored)

    with open(tmp_path, "wb") as fh:
        fh.write(raw)

    doc = {"original_name": original, "stored_name": stored, "format": fmt,
           "size_bytes": len(raw), "uploaded_at": now, "status": "pending",
           "rows_expected": result["rows"], "rows_indexed": 0, "rows_errors": 0}
    try:
        doc["_id"] = ext.db.file_metadata.insert_one(doc).inserted_id
    except PyMongoError:
        os.remove(tmp_path)
        log.exception("could not save file metadata")
        return _error("Base de données indisponible, import annulé.", 503)

    os.replace(tmp_path, os.path.join(target_dir, stored))  # atomic: Logstash sees a complete file
    log.info("file accepted: %s (%d rows)", stored, result["rows"])

    file_id = str(doc["_id"])
    return jsonify(message="Fichier accepté, ingestion en cours.",
                   file=ingestion.serialize(doc),
                   preview=result["preview"],
                   status_url=f"/api/v1/files/{file_id}"), 201


@bp.route("/api/v1/files")
def list_files():
    docs = list(ext.db.file_metadata.find().sort("uploaded_at", -1).limit(50))
    return jsonify(files=[ingestion.serialize(ingestion.refresh(d)) for d in docs])


@bp.route("/api/v1/files/<file_id>")
def get_file(file_id):
    try:
        oid = ObjectId(file_id)
    except InvalidId:
        return _error("Identifiant invalide.", 400)
    doc = ext.db.file_metadata.find_one({"_id": oid})
    if doc is None:
        return _error("Fichier introuvable.", 404)
    return jsonify(ingestion.serialize(ingestion.refresh(doc)))
