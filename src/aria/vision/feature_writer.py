import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

DEFAULT_SCHEMA_PATH = (Path(__file__).resolve().parents[3] / "schemas" / "camera_track.schema.json")

class FeatureWriter:
    def __init__(self, output_path, schema_path=DEFAULT_SCHEMA_PATH):
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = None
        with Path(schema_path).open(encoding="utf-8") as stream:
            schema = json.load(stream)
        Draft202012Validator.check_schema(schema)
        self.validator = Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        )

    def write(self, record):
        self.validator.validate(record)
        if self._stream is None:
            self._stream = self.output_path.open("a", encoding="utf-8")
        self._stream.write(json.dumps(record) + "\n")
        self._stream.flush()

    def close(self):
        if self._stream is not None:
            self._stream.close()
            self._stream = None