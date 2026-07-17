import pytest

from harness.synth.generator import PlantedParams, generate
from harness.synth.questions import emit


@pytest.fixture(scope="session")
def params() -> PlantedParams:
    # smaller than default for test speed; all planted-event months in range
    return PlantedParams(seed=42, n_accounts=300, n_months=18)


@pytest.fixture(scope="session")
def db_path(tmp_path_factory, params):
    path = tmp_path_factory.mktemp("synth") / "business.duckdb"
    generate(path, params)
    return path


@pytest.fixture(scope="session")
def questions(db_path, params):
    return emit(db_path, params)
