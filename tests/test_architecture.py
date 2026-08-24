"""Small dependency tests that keep the inward-pointing architecture honest."""
import ast
from pathlib import Path

PACKAGE = Path("src/open_omada_device_agent")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_domain_modules_do_not_import_adapters_or_infrastructure():
    forbidden = ("adapters", "infrastructure", "openwrt", "subprocess", "config")
    violations = []
    for path in PACKAGE.glob("contexts/**/domain.py"):
        for imported in _imports(path):
            if any(part in imported.split(".") for part in forbidden):
                violations.append(f"{path}: {imported}")
    assert violations == []


def test_application_modules_do_not_import_concrete_openwrt_adapters():
    violations = []
    for path in PACKAGE.glob("contexts/**/application.py"):
        for imported in _imports(path):
            if "openwrt" in imported.lower() or "adapters.outbound" in imported:
                violations.append(f"{path}: {imported}")
    assert violations == []
