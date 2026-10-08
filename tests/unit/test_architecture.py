"""Protect boundaries when adding code or moving modules."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "check_architecture", ROOT / "scripts/check_architecture.py"
)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)

pytestmark = pytest.mark.unit


def test_application_respects_import_boundaries():
    assert checker.violations() == []


@pytest.mark.parametrize(
    "source",
    [
        "from api.websockets.dashboard_ws import KAFKA_TOPICS",
        "def collect():\n    import agents.base_agent",
        "import research.hmm_trading",
        "from src.core.config import settings",
    ],
)
def test_boundary_check_detects_forbidden_imports(tmp_path, source):
    for package in checker.PACKAGES:
        (tmp_path / package).mkdir()
    (tmp_path / "core/example.py").write_text(source)
    assert len(checker.violations(tmp_path)) == 1


@pytest.mark.parametrize(
    "module", ["core.accounting.repository", "connectors.exchanges.paper", "redis.asyncio"]
)
def test_advisory_boundary_prevents_trading_state_access(tmp_path, module):
    for package in checker.PACKAGES:
        (tmp_path / package).mkdir()
    (tmp_path / "api/advisor.py").write_text(f"import {module}\n")
    assert len(checker.violations(tmp_path)) == 1


@pytest.fixture
def source_tree(tmp_path):
    """Build inert source trees; the checker must never import their code."""
    for package in checker.PACKAGES:
        (tmp_path / package).mkdir()
        (tmp_path / package / "__init__.py").write_text("")

    def write(files):
        for name, source in files.items():
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source)
        return tmp_path

    return write


@pytest.mark.parametrize(
    "source",
    [
        "import core.execution.recovery",
        "from ..execution import recovery",
        "from ..execution.recovery import RecoveryCoordinator",
        "from .helper import bridge",
    ],
)
def test_advisory_rejects_relative_and_absolute_execution_imports(source_tree, source):
    root = source_tree(
        {
            "api/advisor.py": "from core.advisory import analysis",
            "core/advisory/__init__.py": "",
            "core/advisory/analysis.py": source,
            "core/advisory/helper.py": "import core.execution.recovery",
            "core/execution/__init__.py": "",
            "core/execution/recovery.py": "",
        }
    )
    # Even an indirect import into an execution package is denied, regardless
    # of whether its leaf module has any side effects today.
    assert any("core.execution.recovery" in error for error in checker.violations(root))


def test_advisory_rejects_transitive_io_and_reports_import_chain(source_tree):
    root = source_tree(
        {
            "api/advisor.py": "from api.security import authorize",
            "api/security.py": "from core.config import settings",
            "core/config.py": "from core.accounting.repository import Ledger",
            "core/accounting/__init__.py": "",
            "core/accounting/repository.py": "",
        }
    )
    errors = checker.violations(root)
    assert any(
        "api.advisor -> api.security -> core.config -> core.accounting.repository" in error
        for error in errors
    )


def test_package_initialization_cannot_hide_execution_io(source_tree):
    root = source_tree(
        {
            "api/advisor.py": "from core.advisory.models import Candle",
            "core/advisory/models.py": "class Candle: pass",
            "core/advisory/__init__.py": "from core.orchestrator import state_manager",
        }
    )
    assert any(
        "api.advisor -> core.advisory.models -> core.advisory -> core.orchestrator" in error
        for error in checker.violations(root)
    )


@pytest.mark.parametrize(
    "source",
    [
        "import aiokafka; aiokafka.AIOKafkaProducer()",
        "import aiokafka as kafka; kafka.AIOKafkaProducer()",
        "from aiokafka import AIOKafkaProducer as Producer; Producer()",
        "import confluent_kafka as kafka; kafka.Producer({})",
        "from confluent_kafka import Producer as Send; Send({})",
    ],
)
def test_advisory_rejects_aliased_producer_capabilities(source_tree, source):
    root = source_tree({"api/advisor.py": source})
    assert any("Producer" in error for error in checker.violations(root))


@pytest.mark.parametrize(
    "source",
    [
        "import importlib; importlib.import_module('core.execution.recovery')",
        "from importlib import import_module as load; load('core.execution.recovery')",
        "__import__('core.execution.recovery')",
        "__import__('core', fromlist=['execution'])",
        "__import__('core.execution', fromlist=['recovery'])",
        "import importlib; importlib.import_module('.recovery', 'core.execution')",
        "import importlib; importlib.import_module('.recovery', package='core.execution')",
        "import importlib; importlib.import_module(name='.recovery', package='core.execution')",
    ],
)
def test_advisory_rejects_dynamic_execution_imports(source_tree, source):
    root = source_tree({"api/advisor.py": source, "core/execution/recovery.py": ""})
    assert any("core.execution" in error for error in checker.violations(root))


@pytest.mark.parametrize(
    "source",
    [
        "import importlib; importlib.import_module(module_name)",
        "from importlib import import_module as load; load(module_name)",
        "__import__(module_name)",
        "import importlib; importlib.import_module('.models', package=package_name)",
        "import importlib; importlib.import_module('.models')",
        "__import__('repository', globals(), locals(), [], 1)",
        "__import__('core', fromlist=modules)",
    ],
)
def test_advisory_unknown_dynamic_import_fails_closed(source_tree, source):
    root = source_tree({"api/advisor.py": source})
    assert any("<unresolved dynamic import>" in error for error in checker.violations(root))


@pytest.mark.parametrize("source", ["from aiokafka import *", "from api.security import *"])
def test_advisory_wildcard_import_cannot_hide_capabilities(source_tree, source):
    root = source_tree({"api/advisor.py": source})
    assert any("<unresolved wildcard import>" in error for error in checker.violations(root))


def test_local_schema_reexport_is_inspected_for_transitive_io(source_tree):
    root = source_tree(
        {
            "api/advisor.py": "from core.data import Candle",
            "core/data/__init__.py": "from .models import *",
            "core/data/models.py": "class Candle: pass",
        }
    )
    assert checker.violations(root) == []
    source_tree({"core/data/models.py": "import connectors.exchanges.paper"})
    assert any("connectors.exchanges.paper" in error for error in checker.violations(root))


def test_inert_schema_exception_does_not_allow_schema_package_io(source_tree):
    root = source_tree(
        {
            "api/advisor.py": "from core.config import settings",
            "core/config.py": "from core.execution.contracts import AccountScope",
            "core/execution/contracts.py": "class AccountScope: pass",
            "core/execution/__init__.py": "from .recovery import RecoveryCoordinator",
            "core/execution/recovery.py": "",
        }
    )
    assert any("core.execution.recovery" in error for error in checker.violations(root))


def test_safe_schema_dependencies_cycles_and_consumer_imports_remain_allowed(source_tree):
    root = source_tree(
        {
            "api/advisor.py": "from api.security import authorize\nfrom aiokafka import AIOKafkaConsumer",
            "api/security.py": "from core.config import settings",
            "core/config.py": "from core.execution.contracts import AccountScope",
            "core/execution/__init__.py": "",
            "core/execution/contracts.py": "from core.accounting.models import OpeningBalances",
            "core/accounting/__init__.py": "",
            "core/accounting/models.py": "class OpeningBalances: pass",
            "core/advisory/__init__.py": "",
            "core/advisory/analysis.py": "from . import models",
            "core/advisory/models.py": "from . import analysis",
        }
    )
    assert checker.violations(root) == []


def test_safe_literal_dynamic_imports_use_the_supplied_package(source_tree):
    root = source_tree(
        {
            "api/advisor.py": (
                "from importlib import import_module as load\n"
                "load('.models', package='core.advisory')\n"
                "__import__('core.advisory', fromlist=['models'])"
            ),
            "core/advisory/__init__.py": "",
            "core/advisory/models.py": "class Candle: pass",
        }
    )
    assert checker.violations(root) == []


def test_checker_parses_source_without_executing_it(source_tree, tmp_path):
    marker = tmp_path / "must-not-exist"
    root = source_tree(
        {
            "api/advisor.py": (
                f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
                "raise RuntimeError('Must never execute inspected modules')"
            )
        }
    )
    assert checker.violations(root) == []
    assert not marker.exists()
