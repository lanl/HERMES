import importlib
from pathlib import Path
from types import ModuleType

import pytest


@pytest.fixture
def run_unpacker_mf_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    repository_root = Path(__file__).resolve().parents[4]
    monkeypatch.syspath_prepend(str(repository_root))
    return importlib.import_module(
        "examples.analysis.unpacking.unpacker_multiple_files.run_unpacker_mf"
    )


def test_bundled_tpx3_file_uses_repository_root(
    run_unpacker_mf_module: ModuleType,
) -> None:
    repository_root = Path(__file__).resolve().parents[4]

    assert run_unpacker_mf_module.REPOSITORY_ROOT == repository_root
    assert run_unpacker_mf_module.SOURCE_TPX3_FILE == (
        repository_root / "tests/data/Example_1kHz_5frames.tpx3"
    )
    assert run_unpacker_mf_module.SOURCE_TPX3_FILE.is_file()
