"""Dependency tests that keep the inward-pointing architecture honest."""
import ast
from pathlib import Path

PACKAGE = Path("src/open_omada_device_agent")
ROOT = "open_omada_device_agent"
COMPATIBILITY_FACADES = {
    "ap_config", "client_tracking", "crypto", "device_commands", "domain", "ecsp",
    "openwrt", "platform_capabilities", "portal_enforcement", "portal_runtime",
    "session_state", "telemetry",
}


def _module_name(path: Path) -> str:
    relative = path.relative_to(PACKAGE).with_suffix("")
    parts = relative.parts[:-1] if relative.name == "__init__" else relative.parts
    return ".".join((ROOT, *parts))


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    current = _module_name(path).split(".")
    if path.name != "__init__.py":
        current = current[:-1]
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = current[: -(node.level - 1)] if node.level > 1 else current
                imported = ".".join((*base, *(node.module or "").split("."))).rstrip(".")
            else:
                imported = node.module or ""
            names.add(imported)
    return names


def _python_files(root: Path):
    return tuple(root.rglob("*.py"))


def test_domain_modules_do_not_import_external_layers():
    forbidden = ("adapters", "infrastructure", "openwrt", "subprocess", "config", "ecsp")
    violations = [
        f"{path}: {imported}"
        for path in PACKAGE.glob("contexts/**/domain.py")
        for imported in _imports(path)
        if any(part in imported.split(".") for part in forbidden)
    ]
    assert violations == []


def test_contexts_do_not_import_compatibility_facades():
    violations = [
        f"{path}: {imported}"
        for path in _python_files(PACKAGE / "contexts")
        for imported in _imports(path)
        if imported.startswith(f"{ROOT}.")
        and imported.split(".")[1] in COMPATIBILITY_FACADES
    ]
    assert violations == []


def test_application_does_not_import_platform_or_flat_adapters():
    forbidden = {"openwrt", "platform_capabilities", "device_commands", "telemetry", "config"}
    violations = [
        f"{path}: {imported}"
        for path in _python_files(PACKAGE / "application")
        for imported in _imports(path)
        if "adapters.outbound" in imported
        or any(part in forbidden for part in imported.split("."))
    ]
    assert violations == []


def test_context_cannot_import_another_context_infrastructure():
    violations = [
        f"{path}: {imported}"
        for path in _python_files(PACKAGE / "contexts")
        for imported in _imports(path)
        if ".contexts." in imported and ".infrastructure" in imported
    ]
    assert violations == []


def test_context_domains_do_not_import_other_context_domains():
    violations = []
    for path in PACKAGE.glob("contexts/*/domain.py"):
        owner = path.parent.name
        for imported in _imports(path):
            marker = f"{ROOT}.contexts."
            if not imported.startswith(marker):
                continue
            target = imported.removeprefix(marker).split(".", 1)[0]
            if target != owner:
                violations.append(f"{path}: {imported}")
    assert violations == []


def test_outbound_adapters_do_not_import_inbound_ecsp():
    violations = [
        f"{path}: {imported}"
        for path in _python_files(PACKAGE / "adapters" / "outbound")
        for imported in _imports(path)
        if ".adapters.inbound" in imported
    ]
    assert violations == []


def test_new_architecture_modules_do_not_use_old_facades():
    roots = (PACKAGE / "application", PACKAGE / "contexts", PACKAGE / "adapters", PACKAGE / "projections", PACKAGE / "bootstrap")
    violations = [
        f"{path}: {imported}"
        for root in roots
        for path in _python_files(root)
        for imported in _imports(path)
        if imported.startswith(f"{ROOT}.") and imported.split(".")[1] in COMPATIBILITY_FACADES
    ]
    assert violations == []
