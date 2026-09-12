import json
from pathlib import Path
from jsonschema import Draft202012Validator

EXPECTED_NODES = {
    "ESP-A1": "A",
    "ESP-A2": "A",
}

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "esp_packet.schema.json"

with SCHEMA_PATH.open(encoding="utf-8") as schema_file:
    PACKET_SCHEMA = json.load(schema_file)

Draft202012Validator.check_schema(PACKET_SCHEMA)
PACKET_VALIDATOR = Draft202012Validator(PACKET_SCHEMA)

REQUIRED_FIELDS = [
    "schema_version",
    "firmware_version",
    "sensor_config",
    "boot_id",
    "node_id",
    "zone",
    "sequence",
    "timestamp_ms",
    "wifi_connected",
    "wifi_rssi_dbm",
    "pir_motion",
    "pir_recent_activity",
]

def parse_packet(data):
    try:
        payload = json.loads(data.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise ValueError(f"Invalid UTF-8: {error}")
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON: {error}")

    if not isinstance(payload, dict):
        raise ValueError("Packet must be a JSON object")

    for field in REQUIRED_FIELDS:
        if field not in payload:
            raise ValueError(f"Missing field: {field}")

    node_id = payload["node_id"]

    if node_id not in EXPECTED_NODES:
        raise ValueError(f"Unknown node_id: {node_id}")

    if payload["zone"] != EXPECTED_NODES[node_id]:
        raise ValueError(f"Wrong zone for {node_id}: expected {EXPECTED_NODES[node_id]}")

    if not isinstance(payload["sequence"], int):
        raise ValueError("sequence must be an integer")

    schema_errors = sorted(PACKET_VALIDATOR.iter_errors(payload),key=lambda error: list(error.absolute_path),)

    if schema_errors:
        error = schema_errors[0]
        field_path = ".".join(str(part) for part in error.absolute_path)
        location = f" at {field_path}" if field_path else ""
        raise ValueError(f"Packet schema validation failed{location}: {error.message}")

    return payload