"""Check static import boundaries without importing or starting any services."""

from __future__ import annotations

import ast
from collections import deque
from importlib.util import resolve_name
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
PACKAGES = {"agents", "api", "backtesting", "connectors", "core", "ml"}
NON_RUNTIME = {"research", "examples", "scripts", "dashboard", "src"}
FORBIDDEN = {
    "core": {"agents", "api", "backtesting", "connectors", "ml"},
    "connectors": {"agents", "api"},
    "backtesting": {"agents", "api"},
    "ml": {"agents", "api"},
}
ADVISORY_PATHS = (
    "core/advisory/",
    "connectors/advisory/",
    "api/advisor.py",
    "api/services/advisory.py",
)
ADVISORY_FORBIDDEN = (
    "agents",
    "core.execution",
    "core.accounting",
    "core.orchestrator",
    "connectors.exchanges",
    "api.main",
    "redis",
    "asyncpg",
    "ccxt",
    "alpaca",
    "ib_insync",
    "aiokafka.AIOKafkaProducer",
    "confluent_kafka.Producer",
)

# Shared Settings currently imports these inert schemas. Permit only indirect
# schema dependencies, still traversing their imports and package initializers.
# This is not permission to import repository, recovery, engine or store modules.
ADVISORY_SCHEMA_DEPENDENCIES = {
    "core.execution",
    "core.execution.contracts",
    "core.accounting",
    "core.accounting.models",
}


def references(tree: ast.AST, module: str, package: bool, local: set[str]) -> list[tuple[str, int]]:
    """Resolve absolute/relative imports and literal dynamic imports without execution."""
    context = module if package else module.rpartition(".")[0]
    result: list[tuple[str, int]] = []
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                result.append((alias.name, node.lineno))
                aliases[alias.asname or alias.name.split(".")[0]] = (
                    alias.name if alias.asname else alias.name.split(".")[0]
                )
        elif isinstance(node, ast.ImportFrom):
            name = node.module or ""
            if node.level:
                name = resolve_name("." * node.level + name, context)
            result.append((name, node.lineno))
            for alias in node.names:
                if alias.name == "*":
                    # A local re-export has an inspectable target, already
                    # recorded above and traversed by the dependency graph.
                    # External/missing targets cannot be checked this way.
                    if name not in local:
                        result.append(("<unresolved wildcard import>", node.lineno))
                    continue
                target = f"{name}.{alias.name}"
                aliases[alias.asname or alias.name] = target
                if target in local or target in ADVISORY_FORBIDDEN:
                    result.append((target, node.lineno))

    def qualified(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            return f"{qualified(node.value)}.{node.attr}"
        return ""

    def argument(node: ast.Call, position: int, keyword: str) -> ast.expr | None:
        if len(node.args) > position:
            return node.args[position]
        return next((item.value for item in node.keywords if item.arg == keyword), None)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = qualified(node.func)
        if name in ADVISORY_FORBIDDEN:
            result.append((name, node.lineno))
        if name in {"importlib.import_module", "__import__"}:
            target_arg = argument(node, 0, "name")
            if not isinstance(target_arg, ast.Constant) or not isinstance(target_arg.value, str):
                result.append(("<unresolved dynamic import>", node.lineno))
                continue
            target = target_arg.value
            if name == "importlib.import_module" and target.startswith("."):
                # import_module resolves against its package argument, not the
                # inspected file's package. Missing/dynamic packages are unsafe.
                package_arg = argument(node, 1, "package")
                if not isinstance(package_arg, ast.Constant) or not isinstance(
                    package_arg.value, str
                ):
                    result.append(("<unresolved dynamic import>", node.lineno))
                    continue
                try:
                    target = resolve_name(target, package_arg.value)
                except (ImportError, ValueError):
                    result.append(("<unresolved dynamic import>", node.lineno))
                    continue
            elif name == "__import__":
                # Relative builtin imports depend on runtime globals. Do not
                # pretend the containing source module establishes those globals.
                level = argument(node, 4, "level")
                if level is not None and not (isinstance(level, ast.Constant) and level.value == 0):
                    result.append(("<unresolved dynamic import>", node.lineno))
                    continue
                fromlist = argument(node, 3, "fromlist")
                if fromlist is not None:
                    if not isinstance(fromlist, ast.List | ast.Tuple) or any(
                        not isinstance(item, ast.Constant) or not isinstance(item.value, str)
                        for item in fromlist.elts
                    ):
                        result.append(("<unresolved dynamic import>", node.lineno))
                        continue
                    for item in fromlist.elts:
                        assert isinstance(item, ast.Constant)
                        if item.value == "*":
                            result.append(("<unresolved wildcard import>", node.lineno))
                        else:
                            result.append((f"{target}.{item.value}", node.lineno))
            if any(item.arg is None for item in node.keywords):
                # **kwargs may override package, level or fromlist semantics.
                result.append(("<unresolved dynamic import>", node.lineno))
            result.append((target, node.lineno))
    return sorted(set(result))


def violations(source_root: Path = SOURCE_ROOT) -> list[str]:
    """Return offending static imports and missing application packages."""
    errors = []
    paths = {}
    for path in sorted(source_root.rglob("*.py")):
        relative = path.relative_to(source_root).with_suffix("")
        parts = relative.parts[:-1] if path.name == "__init__.py" else relative.parts
        paths[".".join(parts)] = path
    graph = {}
    for module, path in paths.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        graph[module] = references(tree, module, path.name == "__init__.py", set(paths))
        # Importing a child executes its package initializers too.
        graph[module].extend(
            (parent, 1)
            for i in range(1, len(module.split(".")))
            if (parent := ".".join(module.split(".")[:i])) in paths
        )
    for package in sorted(PACKAGES):
        directory = source_root / package
        if not directory.is_dir():
            errors.append(f"Missing source package: {package}")
            continue
    for module, edges in graph.items():
        package = module.split(".")[0]
        path = paths[module].relative_to(source_root)
        for target, line in edges:
            if target.split(".")[0] in NON_RUNTIME | FORBIDDEN.get(package, set()):
                errors.append(f"{path}:{line}: {package} must not import {target}")
        if not path.as_posix().startswith(ADVISORY_PATHS):
            continue
        queue = deque([(module, (module,))])
        visited = set()
        while queue:
            current, chain = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            for target, line in graph.get(current, []):
                prohibited = target in {
                    "<unresolved dynamic import>",
                    "<unresolved wildcard import>",
                } or any(target == p or target.startswith(p + ".") for p in ADVISORY_FORBIDDEN)
                if prohibited and not (len(chain) > 1 and target in ADVISORY_SCHEMA_DEPENDENCIES):
                    errors.append(
                        f"{path}: manual research must not import {target}; "
                        f"via {' -> '.join((*chain, target))} ({current}:{line})"
                    )
                elif target in graph:
                    queue.append((target, (*chain, target)))
    return sorted(set(errors))


def main() -> int:
    errors = violations()
    if errors:
        print("\n".join(errors))
        return 1
    print("Architecture boundaries passed for all six application packages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
