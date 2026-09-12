"""fail-closed session collection foundations for active zone a scope"""
from .manifest import (
    ManifestValidationError,
    build_initial_manifest,
    generate_session_id,
    validate_manifest,
    write_manifest_atomic,
)
from .lifecycle import (
    SessionLifecycle,
    SessionLifecycleError,
    validate_incident,
    write_incident_atomic,
)
from .preflight import (
    PauseStopController,
    PreflightConfig,
    PreflightError,
    PreflightReport,
    SensorPacket,
    require_ready,
    run_preflight,
)

__all__ = [
    "ManifestValidationError",
    "PauseStopController",
    "PreflightConfig",
    "PreflightError",
    "PreflightReport",
    "SensorPacket",
    "SessionLifecycle",
    "SessionLifecycleError",
    "build_initial_manifest",
    "generate_session_id",
    "require_ready",
    "run_preflight",
    "validate_manifest",
    "validate_incident",
    "write_incident_atomic",
    "write_manifest_atomic",
]
