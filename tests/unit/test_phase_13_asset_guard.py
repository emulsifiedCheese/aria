"""reviewed source-pin refresh must not disable subsequent drift rejection"""
import pytest
from aria.acceptance import runtime_io
from aria.acceptance.runtime import RuntimeSafetyError

def test_reviewed_deployment_assets_match_all_pins():
    assert runtime_io.verify_assets() == runtime_io.ASSETS

@pytest.mark.parametrize('asset', tuple(runtime_io.ASSETS))
def test_each_asset_still_fails_closed_on_drift(monkeypatch, asset):
    original_hash = runtime_io.file_hash

    def changed_hash(path):
        if path == runtime_io.ROOT / asset:
            return 'simulated-changed-file-digest'
        return original_hash(path)

    monkeypatch.setattr(runtime_io, 'file_hash', changed_hash)
    with pytest.raises(RuntimeSafetyError, match='runtime_asset_changed'):
        runtime_io.verify_assets()
