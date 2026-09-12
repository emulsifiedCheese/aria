import pytest
from aria.collection.activity_labels import map_activity_label

@pytest.mark.parametrize("source", ["Serving", "Typing/Processing"])
def test_historical_serving_and_processing_map_to_combined_label(source):
    assert map_activity_label(source, source_schema_version=2) == "Serving/Processing"

@pytest.mark.parametrize("activity", ["Idle/Waiting", "Reaching/Handling"])
def test_unchanged_historical_labels_map_to_themselves(activity):
    assert map_activity_label(activity, source_schema_version=2) == activity

def test_current_combined_label_is_accepted():
    assert (map_activity_label("Serving/Processing", source_schema_version=3) == "Serving/Processing")

@pytest.mark.parametrize("activity", ["Serving", "Typing/Processing"])
def test_current_schema_rejects_separate_historical_labels(activity):
    with pytest.raises(ValueError, match="Unsupported annotation-v3 activity"):
        map_activity_label(activity, source_schema_version=3)

def test_none_remains_none_for_non_labelled_records():
    assert map_activity_label(None, source_schema_version=2) is None

def test_unknown_schema_version_is_rejected():
    with pytest.raises(ValueError, match="Unsupported annotation schema version"):
        map_activity_label("Idle/Waiting", source_schema_version=1)