import importlib
from pathlib import Path
from types import ModuleType

import pytest


@pytest.fixture
def run_unpacking_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    repository_root = Path(__file__).resolve().parents[4]
    monkeypatch.syspath_prepend(str(repository_root))
    return importlib.import_module("examples.analysis.unpacking.run_unpacking")


def test_bundled_tpx3_file_uses_repository_root(
    run_unpacking_module: ModuleType,
) -> None:
    repository_root = Path(__file__).resolve().parents[4]

    assert run_unpacking_module.REPOSITORY_ROOT == repository_root
    assert run_unpacking_module.SOURCE_TPX3_FILE == (
        repository_root / "tests/data/tpx3/Example_1kHz_5frames.tpx3"
    )
    assert run_unpacking_module.SOURCE_TPX3_FILE.is_file()
