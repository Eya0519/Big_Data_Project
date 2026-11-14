import csv
import io
import ipaddress
import json
from datetime import datetime

CSV_COLUMNS = ["timestamp", "ip_source", "utilisateur", "type_evenement",
               "resultat", "niveau", "ressource", "service", "description"]
JSON_REQUIRED = ["timestamp", "ip_source", "type_evenement", "resultat"]
MAX_ERRORS = 10
PREVIEW_ROWS = 10


class ValidationError(Exception):
    def __init__(self, message, details=None):
        super().__init__(message)
        self.message = message
        self.details = details or []


def _valid_timestamp(value):
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _valid_ip(value):
    try:
        ipaddress.ip_address(str(value))
        return True
    except ValueError:
        return False


def _decode(raw):
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValidationError("Le fichier n'est pas encodé en UTF-8.")
    if not text.strip():
        raise ValidationError("Le fichier est vide.")
    return text


def _finish(errors, rows, preview):
    if errors:
        raise ValidationError(f"{len(errors)} erreur(s) dans le fichier.", errors[:MAX_ERRORS])
    return {"rows": rows, "preview": preview}


def validate_csv(raw):
    text = _decode(raw)
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if header != CSV_COLUMNS:
        raise ValidationError("En-tête CSV invalide.", [
            "Attendu : " + ",".join(CSV_COLUMNS),
            "Reçu : " + ",".join(header or [])])
    errors, preview, rows = [], [], 0
    for line_no, row in enumerate(reader, start=2):
        if not row:
            errors.append(f"Ligne {line_no} : ligne vide")
            continue
        rows += 1
        if len(row) != len(CSV_COLUMNS):
            errors.append(f"Ligne {line_no} : {len(row)} colonnes au lieu de {len(CSV_COLUMNS)}")
            continue
        if len(preview) < PREVIEW_ROWS:
            preview.append(dict(zip(CSV_COLUMNS, row)))
        if not _valid_timestamp(row[0]):
            errors.append(f"Ligne {line_no} : timestamp invalide ({row[0]!r})")
        elif not _valid_ip(row[1]):
            errors.append(f"Ligne {line_no} : adresse IP invalide ({row[1]!r})")
    return _finish(errors, rows, preview)


def validate_json(raw):
    text = _decode(raw)
    if text.lstrip().startswith("["):
        raise ValidationError("Tableau JSON détecté.", [
            "Le fichier doit contenir un objet JSON par ligne (format NDJSON)."])
    errors, preview, rows = [], [], 0
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            errors.append(f"Ligne {line_no} : ligne vide")
            continue
        rows += 1
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"Ligne {line_no} : JSON invalide ({exc.msg})")
            continue
        if not isinstance(obj, dict):
            errors.append(f"Ligne {line_no} : ce n'est pas un objet JSON")
            continue
        if len(preview) < PREVIEW_ROWS:
            preview.append(obj)
        missing = [f for f in JSON_REQUIRED if f not in obj]
        if missing:
            errors.append(f"Ligne {line_no} : champs manquants ({', '.join(missing)})")
        elif not _valid_timestamp(obj["timestamp"]):
            errors.append(f"Ligne {line_no} : timestamp invalide ({obj['timestamp']!r})")
        elif not _valid_ip(obj["ip_source"]):
            errors.append(f"Ligne {line_no} : adresse IP invalide ({obj['ip_source']!r})")
    return _finish(errors, rows, preview)


def validate(fmt, raw):
    return validate_csv(raw) if fmt == "csv" else validate_json(raw)
