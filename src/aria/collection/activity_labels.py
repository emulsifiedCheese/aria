"""versioned activity labels, explicit historical label mapping"""
CURRENT_ACTIVITY_SCHEMA_VERSION = 3
CURRENT_ACTIVITIES = (
    "Serving/Processing",
    "Idle/Waiting",
    "Reaching/Handling",
)

HISTORICAL_V2_ACTIVITY_MAP = {
    "Serving": "Serving/Processing",
    "Typing/Processing": "Serving/Processing",
    "Idle/Waiting": "Idle/Waiting",
    "Reaching/Handling": "Reaching/Handling",
}

def map_activity_label(activity, *, source_schema_version):
    """map one retained activity into current 3-class taxonomy"""
    if activity is None:
        return None
    if source_schema_version == 2:
        try:
            return HISTORICAL_V2_ACTIVITY_MAP[activity]
        except KeyError as error:
            raise ValueError(f"Unsupported annotation-v2 activity: {activity}") from error
    if source_schema_version == CURRENT_ACTIVITY_SCHEMA_VERSION:
        if activity not in CURRENT_ACTIVITIES:
            raise ValueError(f"Unsupported annotation-v3 activity: {activity}")
        return activity
    raise ValueError(f"Unsupported annotation schema version: {source_schema_version}")