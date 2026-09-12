import json
from copy import deepcopy
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = PROJECT_ROOT / "schemas"
SCHEMA_NAMES = ("annotation", "prediction", "incident")

def load_validator(name):
    with (SCHEMA_DIR / f"{name}.schema.json").open(encoding="utf-8") as stream:
        schema = json.load(stream)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())

@pytest.fixture(scope="module", params=SCHEMA_NAMES)
def named_validator(request):
    return request.param, load_validator(request.param)

@pytest.fixture(scope="module")
def annotation_validator():
    return load_validator("annotation")

@pytest.fixture(scope="module")
def prediction_validator():
    return load_validator("prediction")

@pytest.fixture(scope="module")
def incident_validator():
    return load_validator("incident")

@pytest.fixture
def annotation():
    return {
        "schema_version": 3,
        "annotation_id": "annotation_example_0001",
        "session_id": "zone_a_20260731T170000SGT_session01",
        "zone": "A",
        "participant_id": "P0001",
        "local_track_id": 3,
        "window_ids": ["zone_a_1785488400000_1785488402000"],
        "interval_start_sgt": "2026-07-31T17:00:00+08:00",
        "interval_end_sgt": "2026-07-31T17:00:02+08:00",
        "label_status": "labelled",
        "activity": "Serving/Processing",
        "exclusion_reason": None,
        "usable_for_modelling": True,
        "annotator_id": "A001",
        "created_at_sgt": "2026-07-31T18:00:00+08:00",
    }

@pytest.fixture
def prediction():
    return {
        "schema_version": 3,
        "prediction_id": "prediction_example_0001",
        "session_id": "zone_a_20260731T170000SGT_session01",
        "window_id": "zone_a_1785488400000_1785488402000",
        "zone": "A",
        "local_track_id": 3,
        "emitted_at_sgt": "2026-07-31T17:00:02+08:00",
        "model_version": "rf-baseline-v1",
        "preprocessing_version": "zone-a-windows-v1",
        "feature_schema_version": 2,
        "prediction_available": True,
        "predicted_activity": "Serving/Processing",
        "confidence": 0.84,
        "unavailable_reason": None,
        "availability": {
            "camera_available": True,
            "pose_available": True,
            "esp_a1_available": True,
            "esp_a2_available": True,
        },
    }

@pytest.fixture
def incident():
    return {
        "schema_version": 5,
        "incident_id": "incident_example_0001",
        "session_id": "zone_a_20260731T170000SGT_session01",
        "zone": "A",
        "incident_type": "camera_stream_loss",
        "severity": "operational",
        "status": "resolved",
        "started_at_sgt": "2026-07-31T17:10:00+08:00",
        "ended_at_sgt": "2026-07-31T17:10:08+08:00",
        "affected_window_ids": ["zone_a_1785489000000_1785489002000"],
        "actions": [
            "collection_paused",
            "interval_excluded",
            "stream_recovered",
        ],
        "deletion_required": False,
        "deletion_completed": False,
        "deletion_completed_at_sgt": None,
        "recovery_verified": True,
        "resumed_at_sgt": "2026-07-31T17:10:10+08:00",
        "operator_role": "student_researcher",
    }

def assert_invalid(validator, record):
    with pytest.raises(ValidationError):
        validator.validate(record)

def test_collection_schemas_are_valid_draft_2020_12(named_validator):
    _, validator = named_validator
    assert validator.schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"

def test_valid_labelled_annotation(annotation_validator, annotation):
    annotation_validator.validate(annotation)

@pytest.mark.parametrize("historical_label", ["Serving", "Typing/Processing"])
def test_current_annotation_rejects_separate_historical_labels(
    annotation_validator, annotation, historical_label
):
    record = deepcopy(annotation)
    record["activity"] = historical_label
    assert_invalid(annotation_validator, record)

@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("activity", "Supervising"),
        ("participant_id", "Counter Agent Example"),
        ("zone", "B"),
    ],
)
def test_annotation_rejects_retired_scope_and_identity_fields(
    annotation_validator, annotation, field, value
):
    record = deepcopy(annotation)
    record[field] = value
    assert_invalid(annotation_validator, record)

def test_uncertain_annotation_is_explicitly_unusable(annotation_validator, annotation):
    record = deepcopy(annotation)
    record.update(
        label_status="uncertain",
        activity=None,
        exclusion_reason="ambiguous_activity",
        usable_for_modelling=False,
    )
    annotation_validator.validate(record)

    record["usable_for_modelling"] = True
    assert_invalid(annotation_validator, record)

def test_excluded_annotation_cannot_retain_activity(annotation_validator, annotation):
    record = deepcopy(annotation)
    record.update(
        label_status="excluded",
        activity="Serving/Processing",
        exclusion_reason="privacy_incident",
        usable_for_modelling=False,
    )
    assert_invalid(annotation_validator, record)

    record["activity"] = None
    annotation_validator.validate(record)

def test_annotation_rejects_unknown_identity_field(annotation_validator, annotation):
    record = deepcopy(annotation)
    record["participant_name"] = "Example Person"
    assert_invalid(annotation_validator, record)

def test_valid_prediction_with_explicit_availability(prediction_validator, prediction):
    prediction_validator.validate(prediction)

@pytest.mark.parametrize("historical_label", ["Serving", "Typing/Processing"])
def test_current_prediction_rejects_separate_historical_labels(
    prediction_validator, prediction, historical_label
):
    record = deepcopy(prediction)
    record["predicted_activity"] = historical_label
    assert_invalid(prediction_validator, record)

def test_unavailable_prediction_requires_null_output_and_reason(
    prediction_validator, prediction
):
    record = deepcopy(prediction)
    record.update(
        prediction_available=False,
        local_track_id=None,
        predicted_activity=None,
        confidence=None,
        unavailable_reason="missing_camera_track",
    )
    record["availability"]["camera_available"] = False
    record["availability"]["pose_available"] = False
    prediction_validator.validate(record)

    record["predicted_activity"] = "Idle/Waiting"
    assert_invalid(prediction_validator, record)

def test_available_prediction_requires_camera_local_track(
    prediction_validator, prediction
):
    record = deepcopy(prediction)
    record["local_track_id"] = None
    assert_invalid(prediction_validator, record)

@pytest.mark.parametrize("activity", ["Managing", "Walking", "Unknown"])
def test_prediction_rejects_retired_or_unapproved_activity(
    prediction_validator, prediction, activity
):
    record = deepcopy(prediction)
    record["predicted_activity"] = activity
    assert_invalid(prediction_validator, record)

def test_valid_non_identifying_incident(incident_validator, incident):
    incident_validator.validate(incident)

@pytest.mark.parametrize("retired_version", [1, 2, 3, 4])
def test_retired_incident_versions_are_rejected(
    incident_validator, incident, retired_version
):
    record = deepcopy(incident)
    record["schema_version"] = retired_version
    assert_invalid(incident_validator, record)

def test_open_incident_can_remain_unresolved(incident_validator, incident):
    record = deepcopy(incident)
    record.update(
        status="open",
        ended_at_sgt=None,
        recovery_verified=False,
        resumed_at_sgt=None,
    )
    incident_validator.validate(record)

def test_resolved_incident_requires_end_and_verified_recovery(
    incident_validator, incident
):
    record = deepcopy(incident)
    record["ended_at_sgt"] = None
    record["recovery_verified"] = False
    assert_invalid(incident_validator, record)

def test_resolved_incident_requires_type_specific_recovery_action(
    incident_validator, incident
):
    record = deepcopy(incident)
    record["actions"] = ["collection_paused"]
    assert_invalid(incident_validator, record)

@pytest.mark.parametrize(
    "incident_type",
    [
        "non_participant_entry",
        "privacy_boundary_breach",
        "camera_movement",
        "mask_failure",
    ],
)
def test_privacy_incident_requires_critical_severity_and_deletion(
    incident_validator, incident, incident_type
):
    record = deepcopy(incident)
    record.update(
        incident_type=incident_type,
        severity="operational",
        status="open",
        ended_at_sgt=None,
        actions=["collection_paused"],
        deletion_required=False,
        recovery_verified=False,
        resumed_at_sgt=None,
    )
    assert_invalid(incident_validator, record)

    record["severity"] = "privacy_critical"
    assert_invalid(incident_validator, record)

    record["deletion_required"] = True
    incident_validator.validate(record)

def test_resolved_privacy_incident_requires_completed_deletion(
    incident_validator, incident
):
    record = deepcopy(incident)
    record.update(
        incident_type="mask_failure",
        severity="privacy_critical",
        deletion_required=True,
        actions=["collection_paused", "mask_reverified"],
    )
    assert_invalid(incident_validator, record)

def test_completed_deletion_requires_timestamp_and_action(incident_validator, incident):
    record = deepcopy(incident)
    record.update(
        incident_type="privacy_boundary_breach",
        severity="privacy_critical",
        deletion_required=True,
        deletion_completed=True,
        deletion_completed_at_sgt="2026-07-31T17:11:00+08:00",
    )
    record["actions"].extend(
        ["affected_data_deleted", "privacy_boundary_restored"]
    )
    incident_validator.validate(record)

    record["actions"].remove("affected_data_deleted")
    assert_invalid(incident_validator, record)

def test_incident_rejects_names_and_free_text(incident_validator, incident):
    for field in ("participant_name", "description"):
        record = deepcopy(incident)
        record[field] = "Identifying free text is prohibited"
        assert_invalid(incident_validator, record)