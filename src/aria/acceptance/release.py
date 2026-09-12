"""Create and verify a privacy-safe, revisioned Phase 13 release archive."""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tempfile

from aria.timebase import SGT, sgt_now


PROJECT_ROOT = Path(__file__).resolve().parents[3]
INCLUDED_FILES = {
    ".gitignore",
    "AGENTS.md",
    "README.md",
    "firebase.json",
    "requirements.txt",
    "yolov8n-pose.pt",
    "yolov8n.pt",
}
INCLUDED_ROOTS = {
    "config",
    "deployment",
    "docs",
    "schemas",
    "scripts",
    "src",
}
INCLUDED_PREFIXES = {
    "firmware/esp_a",
    "models/README.md",
    "models/phase_11_1/camera_only.joblib",
}
EXCLUDED_NAMES = {".DS_Store", "__pycache__"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
PROHIBITED_MEDIA_SUFFIXES = {
    ".aac", ".avi", ".heic", ".jpeg", ".jpg", ".m4a", ".mkv",
    ".mov", ".mp3", ".mp4", ".png", ".wav", ".webm",
}
TEXT_SUFFIXES = {
    "", ".cfg", ".css", ".html", ".ino", ".js", ".json", ".md",
    ".py", ".sha256", ".toml", ".txt", ".yaml", ".yml",
}
SECRET_PATTERNS = {
    "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "firebase_api_key": re.compile(rb"AIza[0-9A-Za-z_-]{20,}"),
    "aws_access_key": re.compile(rb"AKIA[0-9A-Z]{16}"),
    "github_token": re.compile(rb"gh[pousr]_[A-Za-z0-9]{20,}"),
}
EMAIL_PATTERN = re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
WIFI_PATTERN = re.compile(
    rb"(WIFI_SSID|WIFI_PASSWORD)\s*=\s*\"([^\"]*)\""
)


class Phase13ReleaseError(RuntimeError):
    """Raised when a release cannot be frozen or verified safely."""


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_included(relative: PurePosixPath) -> bool:
    text = relative.as_posix()
    return (
        text in INCLUDED_FILES
        or relative.parts[0] in INCLUDED_ROOTS
        or any(text == prefix or text.startswith(prefix + "/") for prefix in INCLUDED_PREFIXES)
    )


def collect_release_files(project_root: Path = PROJECT_ROOT) -> list[Path]:
    """Return the deterministic active-release allowlist."""
    files = []
    for path in project_root.rglob("*"):
        if not path.is_file():
            continue
        relative = PurePosixPath(path.relative_to(project_root).as_posix())
        if not _is_included(relative):
            continue
        if any(part in EXCLUDED_NAMES for part in relative.parts):
            continue
        if relative.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        if relative.suffix.lower() in PROHIBITED_MEDIA_SUFFIXES:
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(project_root).as_posix())


def build_file_records(files: list[Path], project_root: Path = PROJECT_ROOT) -> list[dict]:
    return [
        {
            "path": path.relative_to(project_root).as_posix(),
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
        }
        for path in files
    ]


def source_revision(records: list[dict]) -> str:
    canonical = json.dumps(records, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "source-tree-sha256:" + sha256(canonical).hexdigest()


def scan_release(files: list[Path], project_root: Path = PROJECT_ROOT) -> dict:
    secret_findings = []
    identity_findings = []
    media_findings = []
    for path in files:
        relative = path.relative_to(project_root).as_posix()
        suffix = path.suffix.lower()
        if suffix in PROHIBITED_MEDIA_SUFFIXES:
            media_findings.append(relative)
            continue
        lower_name = path.name.lower()
        if lower_name == ".env" or any(term in lower_name for term in ("service-account", "credentials.json")):
            secret_findings.append({"path": relative, "rule": "sensitive_filename"})
        if suffix not in TEXT_SUFFIXES:
            continue
        payload = path.read_bytes()
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(payload):
                secret_findings.append({"path": relative, "rule": name})
        for match in WIFI_PATTERN.finditer(payload):
            variable = match.group(1).decode("ascii")
            value = match.group(2).decode("utf-8", errors="replace")
            if variable == "WIFI_PASSWORD" and value and not value.startswith(("REPLACE_", "YOUR_", "<")):
                secret_findings.append({"path": relative, "rule": "wifi_literal"})
        if EMAIL_PATTERN.search(payload):
            identity_findings.append({"path": relative, "rule": "email_address"})
    return {
        "secret_scan_passed": not secret_findings,
        "identity_and_media_scan_passed": not identity_findings and not media_findings,
        "secret_findings": secret_findings,
        "identity_findings": identity_findings,
        "media_findings": media_findings,
    }


def _manifest_bytes(manifest: dict) -> bytes:
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_archive(
    archive_path: Path,
    files: list[Path],
    manifest: dict,
    project_root: Path = PROJECT_ROOT,
) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "w", format=tarfile.PAX_FORMAT) as archive:
        for path in files:
            relative = path.relative_to(project_root).as_posix()
            info = archive.gettarinfo(str(path), arcname=f"aria/{relative}")
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            info.mode = 0o755 if relative.startswith("scripts/") and path.stat().st_mode & 0o111 else 0o644
            with path.open("rb") as stream:
                archive.addfile(info, stream)
        payload = _manifest_bytes(manifest)
        info = tarfile.TarInfo("aria/RELEASE_MANIFEST.json")
        info.size = len(payload)
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        info.mtime = 0
        info.mode = 0o644
        archive.addfile(info, io.BytesIO(payload))


def verify_clean_archive(archive_path: Path, python_executable: str) -> dict:
    """Extract to a fresh folder, verify every hash, then run the synthetic demo."""
    with tempfile.TemporaryDirectory(prefix="aria-phase13-release-") as directory:
        extraction = Path(directory)
        with tarfile.open(archive_path, "r") as archive:
            archive.extractall(extraction, filter="data")
        root = extraction / "aria"
        manifest = json.loads((root / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
        records = manifest["files"]
        hashes_verified = all(
            (root / record["path"]).is_file()
            and _sha256(root / record["path"]) == record["sha256"]
            and (root / record["path"]).stat().st_size == record["size_bytes"]
            for record in records
        )
        revision_verified = source_revision(records) == manifest["code_revision"]
        process = subprocess.run(
            [python_executable, "scripts/run_phase_13.py", "--input-scope", "synthetic"],
            cwd=root,
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin", "PYTHONPATH": "src"},
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        synthetic_passed = (
            process.returncode == 0
            and '"live_hardware_used": false' in process.stdout
            and '"participant_data_used": false' in process.stdout
            and '"external_test_accessed": false' in process.stdout
            and '"clean_stop_counts": true' in process.stdout
        )
        return {
            "archive_extracted_to_fresh_directory": True,
            "file_hashes_verified": hashes_verified,
            "source_revision_verified": revision_verified,
            "synthetic_demonstration_passed": synthetic_passed,
            "synthetic_exit_code": process.returncode,
            "clean_environment_verified": hashes_verified and revision_verified and synthetic_passed,
        }


def freeze_release(output_root: Path, python_executable: str, *, now: datetime | None = None) -> dict:
    timestamp = (now or sgt_now()).astimezone(SGT).strftime("%Y%m%dT%H%M%S")
    files = collect_release_files()
    if not files:
        raise Phase13ReleaseError("release allowlist is empty")
    records = build_file_records(files)
    revision = source_revision(records)
    release_dir = output_root / f"release_{timestamp}_{revision.split(':', 1)[1][:8]}"
    release_dir.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema_version": 1,
        "release_id": "zone-a-phase13-release-v1",
        "generated_at_sgt": (now or sgt_now()).astimezone(SGT).isoformat(timespec="milliseconds"),
        "code_revision": revision,
        "file_count": len(records),
        "files": records,
    }
    scan = scan_release(files)
    if not scan["secret_scan_passed"] or not scan["identity_and_media_scan_passed"]:
        raise Phase13ReleaseError("release privacy scan failed")
    archive = release_dir / f"aria_phase13_{revision.split(':', 1)[1][:12]}.tar"
    write_archive(archive, files, manifest)
    clean = verify_clean_archive(archive, python_executable)
    if not clean["clean_environment_verified"]:
        raise Phase13ReleaseError("clean-environment verification failed")
    report = {
        "schema_version": 1,
        "release_id": manifest["release_id"],
        "generated_at_sgt": manifest["generated_at_sgt"],
        "code_revision": revision,
        "archive": archive.name,
        "archive_sha256": _sha256(archive),
        "file_count": len(records),
        "secret_scan_passed": True,
        "identity_and_media_scan_passed": True,
        "scan_findings": {key: scan[key] for key in ("secret_findings", "identity_findings", "media_findings")},
        **clean,
        "participant_data_used": False,
        "external_test_accessed": False,
        "live_hardware_used": False,
    }
    (release_dir / "release_manifest.json").write_bytes(_manifest_bytes(manifest))
    (release_dir / "release_verification.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"directory": str(release_dir), "manifest": manifest, "report": report}
