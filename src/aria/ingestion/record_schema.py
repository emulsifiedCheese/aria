"""validation for locally stored esp receive envs"""
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_DIR = PROJECT_ROOT / "schemas"
PACKET_SCHEMA_PATH = SCHEMA_DIR / "esp_packet.schema.json"
RECORD_SCHEMA_PATH = SCHEMA_DIR / "esp_record.schema.json"

def _load_schema(path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)

PACKET_SCHEMA = _load_schema(PACKET_SCHEMA_PATH)
RECORD_SCHEMA = _load_schema(RECORD_SCHEMA_PATH)
Draft202012Validator.check_schema(PACKET_SCHEMA)
Draft202012Validator.check_schema(RECORD_SCHEMA)

SCHEMA_REGISTRY = Registry().with_resource(
    PACKET_SCHEMA["$id"],
    Resource.from_contents(PACKET_SCHEMA),
)
RECORD_VALIDATOR = Draft202012Validator(
    RECORD_SCHEMA,
    registry=SCHEMA_REGISTRY,
    format_checker=FormatChecker(),
)

def validate_esp_record(record):

    errors = sorted(RECORD_VALIDATOR.iter_errors(record), key=lambda error: list(error.path))
    if errors:
        error = errors[0]
        location = ""
        if error.absolute_path:
            location = " at " + ".".join(str(part) for part in error.absolute_path)
        raise ValueError(f"ESP record schema validation failed{location}: {error.message}")
    return record