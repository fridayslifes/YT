"""Change-propagation index: what still points at a thing you changed or deleted.

The removal of the thumbnail subsystem on 2026-11-01 is why this exists. Deleting
`tools/thumbnail_studio.py` left references behind in six source files, three test files, six
documents and two requirements files, and no existing gate noticed: `ruff` only sees code, the
contract tests only read `project.json`, and `audit` only walks projects. Every leftover was a
command a later agent would run and fail on.

This indexes the repo - python imports and symbols, argparse flags, worker kinds and verifier
names, asset paths, document command lines and line citations - so the master can answer
two questions with evidence:

    python tools/master.py impact --name thumbnail_studio   # who still refers to this?
    python tools/master.py impact --all                     # what is already dangling?

`find_stale` is what the `consistency` verifier calls, so a dangling reference fails `audit` and
the release gate instead of surfacing as a runtime error in the middle of a production run.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path

SKIP_DIRS = {
    ".venv", "venv", "models", "__pycache__", ".git", ".orchestrator",
    ".pytest_cache", ".ruff_cache", "node_modules", ".agents", ".superpowers", "superpowers", "output", "cache", "videos",
    "kokoro_models", "fonts",
}
ASSET_EXT = {
    ".jpg", ".jpeg", ".png", ".svg", ".gif", ".mp4", ".mov", ".wav", ".mp3", ".ttf", ".otf",
    ".ttc", ".json", ".md", ".txt", ".srt", ".vtt", ".onnx", ".bin", ".obj",
}
# A line citation - a script name followed by a colon and a line number - as written in comments,
# docstrings and documents.
CITATION_RE = re.compile(r"(?P<name>[\w][\w./-]*\.py):(?P<line>\d+)")
# A command line in a document that runs one of the repo's scripts.
DOC_CMD_RE = re.compile(r"(?:\.venv/bin/)?python3?\s+(?P<script>[\w./-]+\.py)(?P<rest>[^\n]*)")
FLAG_RE = re.compile(r"--[a-z][a-z0-9-]*")
ASSET_RE = re.compile(r"[\w./-]*\.(?:" + "|".join(sorted(e.lstrip(".") for e in ASSET_EXT)) + r")\b")
PY_NAME_RE = re.compile(r"\b([a-z_][a-z0-9_]*)\.py\b")
# A generated filename (`thumbnail_{aspect}_A.jpg`) is not a reference to a file on disk.
PLACEHOLDER_RE = re.compile(r"[{*]|\.\.\.")
# Only these prefixes promise a checked-in file. Anything under shorts/, long_form/, output/ or
# cache/ is something a run writes, so its absence is not a dangling reference.
REPO_ASSET_PREFIXES = ("tools/", "channel_assets/", "assets/", "tests/", "models/")


@dataclass(frozen=True)
class Site:
    """One reference to one name, at one place in the repo."""

    file: str
    line: int
    kind: str
    detail: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: [{self.kind}] {self.detail}"

    def as_dict(self) -> dict:
        return {"file": self.file, "line": self.line, "kind": self.kind, "detail": self.detail}


def _walk(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    out: list[Path] = []
    for path in sorted(root.rglob("*")):
        rel_parts = path.relative_to(root).parts
        if any(part in SKIP_DIRS for part in rel_parts):
            continue
        try:
            if not path.is_file():
                continue
        except OSError:
            continue
        if path.suffix.lower() not in suffixes:
            continue
        out.append(path)
    return out


def _module_exists(index: "Index", dotted: str) -> bool:
    """Whether a dotted `tools.*` name resolves. Anything outside tools/ is out of scope."""
    if not dotted:
        return True
    head = dotted.split(".")[0]
    if head not in {"tools", "tests", "test"}:
        return True
    if dotted == "tools":  # PEP 420 namespace package: has no __init__.py by design.
        return True
    if any(mod == dotted or mod.startswith(f"{dotted}.") for mod in index.modules):
        return True
    # `tools.tracker.update_tracker_row` is an attribute of a module that does exist - but the bare
    # namespace does not count as that parent, or every `from tools import gone` would be excused.
    while "." in dotted:
        dotted = dotted.rsplit(".", 1)[0]
        if dotted == "tools":
            return False
        if dotted in index.modules or any(mod.startswith(f"{dotted}.") for mod in index.modules):
            return True
    return False


class Index:
    """Everything the repo claims about itself, keyed for lookup."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.py_files = _walk(self.root, (".py",))
        self.doc_files = _walk(self.root, (".md", ".txt", ".toml", ".cfg"))
        self.on_disk: set[str] = {
            str(p.relative_to(self.root).as_posix())
            for p in _walk(self.root, tuple(sorted(ASSET_EXT)) + (".py", ".cfg", ".toml"))
        }
        self.basenames: set[str] = {Path(p).name for p in self.on_disk}
        self.modules: set[str] = set()
        self.symbols: set[str] = set()
        self.flags: dict[str, set[str]] = {}
        self.worker_kinds: set[str] = set()
        self.verifier_names: set[str] = set()
        self.refs: dict[str, list[Site]] = {}
        self.citations: list[tuple[str, int, str, int]] = []
        self.doc_commands: list[tuple[str, int, str, set[str], str]] = []
        self.asset_paths: list[tuple[str, int, str]] = []
        self.subcommands_by_file: dict[str, set[str]] = {}
        self.workflow_task_ids: dict[tuple[str, str], set[str]] = {}
        self.dynamic_task_scopes: set[tuple[str, str]] = set()
        self.workflow_dependencies: list[tuple[tuple[str, str], str, Site]] = []
        self._build()

    # ------------------------------------------------------------------ #
    # construction
    # ------------------------------------------------------------------ #
    def _add_ref(self, name: str, rel: str, line: int, kind: str, detail: str) -> None:
        site = Site(rel, line, kind, detail)
        bucket = self.refs.setdefault(name, [])
        if site not in bucket:
            bucket.append(site)

    def _build(self) -> None:
        for path in self.py_files:
            rel = path.relative_to(self.root).as_posix()
            if rel.startswith("tools/"):
                mod = rel[:-3].replace("/", ".")
                self.modules.add(mod[: -len(".__init__")] if mod.endswith(".__init__") else mod)
            self._index_python(path, rel)
        for path in self.doc_files:
            self._index_doc(path, path.relative_to(self.root).as_posix())

    def _index_python(self, path: Path, rel: str) -> None:
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            raise SyntaxError(f"{rel} does not parse: {exc}") from exc

        def line_at(offset: int) -> int:
            return text.count("\n", 0, offset) + 1

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.symbols.add(node.name)
                self._add_ref(node.name, rel, node.lineno, "definition", f"def/class {node.name}")
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.symbols.add(target.id)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    self._add_ref(alias.name, rel, node.lineno, "import", f"import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level:
                    package = rel.rsplit("/", 1)[0].replace("/", ".")
                    module = f"{package}.{module}" if module else package
                for alias in node.names:
                    self._add_ref(alias.name, rel, node.lineno, "import", f"from {module or '.'} import {alias.name}")
                    if module:
                        self._add_ref(f"{module}.{alias.name}", rel, node.lineno, "import", f"from {module} import {alias.name}")
                if module:
                    self._add_ref(module, rel, node.lineno, "import", f"from {module} import ...")
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                self._index_string(node.value, rel, getattr(node, "lineno", 1))
            elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
                # `<dir constant> / "name.py"` is how the pipeline invokes a checked-in sibling
                # script; a bare ".py" string anywhere else is prose or a runtime temp file.
                if isinstance(node.right, ast.Constant) and isinstance(node.right.value, str):
                    value = node.right.value
                    if value.endswith(".py") and re.fullmatch(r"[\w-]+\.py", value):
                        self._add_ref(value, rel, node.lineno, "script-ref", value)

        for match in re.finditer(r'add_argument\(\s*["\'](--[a-z0-9-]+)["\']', text):
            self.flags.setdefault(rel, set()).add(match.group(1))
            self._add_ref(match.group(1), rel, line_at(match.start()), "flag-declared", match.group(1))

        # argparse subcommands live in the CLI module, not in the thin entry script that names it.
        for match in re.finditer(r'add_parser\(\s*["\']([\w-]+)["\']', text):
            self.subcommands_by_file.setdefault(rel, set()).add(match.group(1))
            self._add_ref(f"subcommand:{match.group(1)}", rel, line_at(match.start()), "subcommand-declared", match.group(1))

        if rel.endswith("orchestrator/workers.py"):
            for match in re.finditer(r'^\s{4}kind\s*=\s*["\']([\w-]+)["\']', text, re.MULTILINE):
                self.worker_kinds.add(match.group(1))
        if rel.endswith("orchestrator/verifiers.py"):
            for match in re.finditer(r'@verifier\(\s*["\']([\w-]+)["\']', text):
                self.verifier_names.add(match.group(1))
        if rel.endswith("orchestrator/workflows.py"):
            for match in re.finditer(r'kind\s*=\s*["\']([\w-]+)["\']', text):
                self._add_ref(f"worker:{match.group(1)}", rel, line_at(match.start()), "dag-kind", f'kind="{match.group(1)}"')
            for match in re.finditer(r'verifiers\s*=\s*\[([^\]]*)\]', text):
                for name in re.findall(r'["\']([\w-]+)["\']', match.group(1)):
                    self._add_ref(f"verifier:{name}", rel, line_at(match.start()), "dag-verifier", f'verifiers=["{name}"]')
            self._index_workflow_tasks(tree, rel)

        for match in CITATION_RE.finditer(text):
            self.citations.append((rel, line_at(match.start()), match.group("name"), int(match.group("line"))))

    def _index_workflow_tasks(self, tree: ast.AST, rel: str) -> None:
        """Keep literal TaskSpec declarations and dependencies in their defining function.

        Named local task factories contribute to their callers. Dynamic task lists are
        checked by MasterAgent.validate at runtime; unrelated workflows cannot satisfy
        each other's dependencies.
        """
        definitions = {}
        named_calls = []
        dependencies = []

        def is_task_spec(node: ast.AST) -> bool:
            return (
                isinstance(node, ast.Name) and node.id == "TaskSpec"
                or isinstance(node, ast.Attribute) and node.attr == "TaskSpec"
            )

        def visit(node: ast.AST, scope: str = "<module>") -> None:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                parent_scope = scope
                scope = f"{scope}.{node.name}:{node.lineno}"
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    definitions[(parent_scope, node.name)] = (rel, scope)
            owner = (rel, scope)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                named_calls.append((owner, node.func.id))
            if isinstance(node, ast.Call) and is_task_spec(node.func):
                keywords = {kw.arg: kw.value for kw in node.keywords}
                identifier = keywords.get("id", node.args[0] if node.args else None)
                if isinstance(identifier, ast.Constant) and isinstance(identifier.value, str):
                    self.workflow_task_ids.setdefault(owner, set()).add(identifier.value)
                    self._add_ref(
                        f"task:{identifier.value}", rel, node.lineno, "dag-task", f'id="{identifier.value}"'
                    )
                else:
                    self.dynamic_task_scopes.add(owner)
                declared_dependencies = keywords.get("depends_on")
                if isinstance(declared_dependencies, (ast.List, ast.Tuple)):
                    for dependency in declared_dependencies.elts:
                        if isinstance(dependency, ast.Constant) and isinstance(dependency.value, str):
                            name = dependency.value
                            detail = f'depends_on=["{name}"]'
                            site = Site(rel, dependency.lineno, "dag-dependency", detail)
                            dependencies.append((owner, name, site))
                            self._add_ref(f"task:{name}", rel, dependency.lineno, "dag-dependency", detail)
            elif (
                isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "from_dict" and is_task_spec(node.func.value)
            ):
                self.dynamic_task_scopes.add(owner)
            for child in ast.iter_child_nodes(node):
                visit(child, scope)

        visit(tree)

        calls = {}
        callers = {}
        for owner, name in named_calls:
            scope = owner[1]
            while True:
                factory = definitions.get((scope, name))
                if factory is not None:
                    if factory != owner:
                        calls.setdefault(owner, set()).add(factory)
                        callers.setdefault(factory, set()).add(owner)
                    break
                if scope == "<module>":
                    break
                scope = scope.rsplit(".", 1)[0]

        # Resolve chains of factories without executing workflow code. Only actual
        # calls transfer declarations; an unused helper remains an unrelated scope.
        changed = True
        while changed:
            changed = False
            for owner, factories in calls.items():
                for factory in factories:
                    provided = self.workflow_task_ids.get(factory, set())
                    known = self.workflow_task_ids.setdefault(owner, set())
                    if not provided <= known:
                        known.update(provided)
                        changed = True
                    if factory in self.dynamic_task_scopes and owner not in self.dynamic_task_scopes:
                        self.dynamic_task_scopes.add(owner)
                        changed = True

        def contexts(owner, seen=frozenset()):
            parents = callers.get(owner, set()) - seen
            if not parents:
                return {owner}
            return {context for parent in parents for context in contexts(parent, seen | {owner})}

        for owner, name, site in dependencies:
            for context in sorted(contexts(owner)):
                self.workflow_dependencies.append((context, name, site))

    def _index_string(self, value: str, rel: str, line: int) -> None:
        if len(value) > 200 or "\n" in value or PLACEHOLDER_RE.search(value):
            return
        if value.startswith(REPO_ASSET_PREFIXES) and Path(value).suffix.lower() in ASSET_EXT:
            self.asset_paths.append((rel, line, value))
            self._add_ref(Path(value).name, rel, line, "asset-ref", value)

    def _index_doc(self, path: Path, rel: str) -> None:
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            for match in DOC_CMD_RE.finditer(line):
                script = match.group("script")
                rest = match.group("rest")
                flags = set(FLAG_RE.findall(rest))
                positional = [tok for tok in rest.split() if not tok.startswith("-")]
                subcommand = positional[0] if positional else ""
                self.doc_commands.append((rel, number, Path(script).name, flags, subcommand))
                self._add_ref(Path(script).name, rel, number, "doc-command", line.strip()[:120])
            for match in CITATION_RE.finditer(line):
                self.citations.append((rel, number, match.group("name"), int(match.group("line"))))
            for match in ASSET_RE.finditer(line):
                name = match.group(0)
                if PLACEHOLDER_RE.search(name):
                    continue
                if name.startswith(REPO_ASSET_PREFIXES):
                    self.asset_paths.append((rel, number, name))
                    self._add_ref(Path(name).name, rel, number, "doc-asset", name)
            for match in PY_NAME_RE.finditer(line):
                self._add_ref(f"{match.group(1)}.py", rel, number, "doc-script", f"{match.group(1)}.py")


# ---------------------------------------------------------------------- #
# staleness checks
# ---------------------------------------------------------------------- #
@dataclass
class Finding:
    rule: str
    detail: str
    sites: list[Site]

    def as_dict(self) -> dict:
        return {"rule": self.rule, "detail": self.detail, "sites": [s.as_dict() for s in self.sites]}

    def in_code(self) -> bool:
        """Whether something in `tools/` would fail, as opposed to a document that has drifted."""
        return any(
            site.file.endswith(".py") and site.kind != "citation" or site.kind in {"import", "script-ref"}
            for site in self.sites
        )

    def __str__(self) -> str:
        where = "; ".join(str(s) for s in self.sites[:3])
        return f"[{self.rule}] {self.detail} -> {where}"


def check_broken_imports(index: Index) -> list[Finding]:
    findings = []
    for name, sites in sorted(index.refs.items()):
        if name.endswith(".py"):
            continue  # a filename, judged by check_missing_scripts instead
        if not (name == "tools" or name.startswith(("tools.", "tests.", "test."))):
            continue
        if _module_exists(index, name):
            continue
        if Path(name.split(".")[-1]).with_suffix(".py").name in index.basenames:
            continue
        findings.append(Finding("broken-import", f"cannot resolve import of {name}", sites))
    return findings


def check_missing_scripts(index: Index) -> list[Finding]:
    """A checked-in .py file referenced by name that is not in the repo.

    Skipped on purpose: tests cite fixture filenames they create themselves, and a name starting
    with an underscore is a temp file the code writes before running it (Blender's render script).
    """
    findings = []
    for name, sites in sorted(index.refs.items()):
        if not name.endswith(".py") or name in {"__init__.py", "__main__.py"} or name.startswith("_"):
            continue
        if name in index.basenames:
            continue
        live = [s for s in sites if not s.file.startswith("tests/")]
        if not live:
            continue
        findings.append(Finding("missing-script", f"{name} is referenced but does not exist", live))
    return findings


def check_documented_flags(index: Index) -> list[Finding]:
    """A document that shows a flag or subcommand the script it names does not accept."""
    findings = []
    for doc, number, script, flags, subcommand in index.doc_commands:
        owners = [rel for rel in index.flags if Path(rel).name == script]
        if script == "master.py" and not owners:
            # The thin entry point delegates to the CLI module, which owns the argparse surface.
            owners = [rel for rel in index.flags if Path(rel).name == "cli.py"]
        if not owners:
            continue
        declared = set().union(*(index.flags[rel] for rel in owners))
        unknown = sorted(flag for flag in flags if flag not in declared)
        if unknown:
            findings.append(
                Finding(
                    "doc-unknown-flag",
                    f"{script} does not accept {', '.join(unknown)}",
                    [Site(doc, number, "doc-command", " ".join(sorted(flags)))],
                )
            )
        subs = set().union(*(index.subcommands_by_file.get(rel, set()) for rel in owners))
        if subcommand and subs and re.fullmatch(r"[a-z][a-z-]*", subcommand) and subcommand not in subs:
            findings.append(
                Finding(
                    "doc-unknown-subcommand",
                    f"{script} has no subcommand {subcommand!r} (it has: {', '.join(sorted(subs))})",
                    [Site(doc, number, "doc-command", subcommand)],
                )
            )
    return findings


def check_drifted_citations(index: Index) -> list[Finding]:
    """A `path.py:NN` citation whose file is gone or whose line no longer exists."""
    line_count: dict[str, int] = {}
    findings = []
    for citing, number, target, line in index.citations:
        target_name = Path(target).name
        resolved = next((p for p in index.on_disk if Path(p).name == target_name and p.endswith(target)), None)
        if resolved is None:
            resolved = next((p for p in index.on_disk if Path(p).name == target_name), None)
        if resolved is None:
            findings.append(
                Finding(
                    "citation-missing-file",
                    f"{target}:{line} cites a file that is gone",
                    [Site(citing, number, "citation", f"{target}:{line}")],
                )
            )
            continue
        if resolved not in line_count:
            text = (index.root / resolved).read_text(encoding="utf-8", errors="replace")
            line_count[resolved] = len(text.splitlines())
        if line > line_count[resolved]:
            findings.append(
                Finding(
                    "citation-past-end-of-file",
                    f"{target}:{line} is past line {line_count[resolved]} of {resolved}",
                    [Site(citing, number, "citation", f"{target}:{line}")],
                )
            )
    return findings


def check_registries(index: Index) -> list[Finding]:
    """A DAG task naming a worker kind, verifier or dependency that is not registered."""
    findings = []
    for name, sites in sorted(index.refs.items()):
        if name.startswith("worker:") and index.worker_kinds:
            kind = name.split(":", 1)[1]
            if kind not in index.worker_kinds:
                findings.append(Finding("unregistered-worker", f'no worker has kind="{kind}"', sites))
        elif name.startswith("verifier:") and index.verifier_names:
            verifier = name.split(":", 1)[1]
            if verifier not in index.verifier_names:
                findings.append(Finding("unregistered-verifier", f"no verifier named {verifier!r}", sites))
    for owner, task, site in index.workflow_dependencies:
        if task not in index.workflow_task_ids.get(owner, set()) and owner not in index.dynamic_task_scopes:
            findings.append(Finding(
                "unknown-task-dependency", f'nothing provides task id "{task}" in {owner[1]}', [site]
            ))
    return findings


def check_missing_assets(index: Index) -> list[Finding]:
    """A checked-in asset path named by code or a document that is not on disk."""
    grouped: dict[str, list[Site]] = {}
    for rel, line, literal in index.asset_paths:
        if (index.root / literal).exists():
            continue
        grouped.setdefault(literal, []).append(Site(rel, line, "asset-path", literal))
    return [
        Finding("missing-asset", f"{literal} is referenced but is not on disk", sites)
        for literal, sites in sorted(grouped.items())
    ]


def find_stale(index: Index) -> list[Finding]:
    findings: list[Finding] = []
    findings += check_broken_imports(index)
    findings += check_missing_scripts(index)
    findings += check_documented_flags(index)
    findings += check_drifted_citations(index)
    findings += check_registries(index)
    findings += check_missing_assets(index)
    return sorted(findings, key=lambda f: (f.rule, f.detail))


# A dangling import, a script the code shells out to, or a registry name nothing provides is a
# command that fails when it runs. The same name surviving only in prose is drift worth fixing, not
# a reason to stop a release - documents are cleared by `./check.sh impact`, not by the gate.
CRITICAL_RULES = {
    "broken-import",
    "missing-script",
    "unregistered-worker",
    "unregistered-verifier",
    "unknown-task-dependency",
}


def severity(finding: Finding) -> str:
    if finding.rule not in CRITICAL_RULES:
        return "warning"
    if finding.rule == "missing-script" and not finding.in_code():
        return "warning"
    return "critical"


def split_findings(findings: list[Finding]) -> tuple[list[Finding], list[Finding]]:
    critical = [f for f in findings if severity(f) == "critical"]
    return critical, [f for f in findings if severity(f) != "critical"]


def impact(index: Index, name: str | None = None, path: str | None = None) -> list[Site]:
    """Every site that still refers to `name` - a module, symbol, script, flag or asset."""
    target = name or (Path(path).name if path else None)
    if not target:
        raise ValueError("impact needs --name or --path")
    stem = re.sub(r"\.(py|md|json|txt|toml)$", "", target)
    dotted = f"tools.{stem}"
    sites: list[Site] = []
    for key, found in index.refs.items():
        tail = key.split(":")[-1]
        if key in {target, stem, dotted, f"{stem}.py", f"{dotted}.py"} or tail in {target, stem, f"{stem}.py"}:
            sites.extend(found)
    return sorted(set(sites), key=lambda s: (s.file, s.line))


def summary(index: Index) -> dict:
    return {
        "python_files": len(index.py_files),
        "doc_files": len(index.doc_files),
        "modules": len(index.modules),
        "symbols": len(index.symbols),
        "flags": sum(len(v) for v in index.flags.values()),
        "referenced_names": len(index.refs),
        "doc_commands": len(index.doc_commands),
        "citations": len(index.citations),
        "subcommands": sorted({s for subs in index.subcommands_by_file.values() for s in subs}),
        "worker_kinds": sorted(index.worker_kinds),
        "verifiers": sorted(index.verifier_names),
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Trace what a change touches across the repo")
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument("--name", help="Module, symbol, script, flag or asset name to trace")
    ap.add_argument("--path", help="Repository path to trace (same as --name, by file)")
    ap.add_argument("--all", action="store_true", help="List every dangling reference instead")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    index = Index(Path(args.root))
    if args.all or not (args.name or args.path):
        findings = find_stale(index)
        if args.json:
            print(json.dumps({"stats": summary(index), "findings": [f.as_dict() for f in findings]}, indent=2))
        else:
            print(json.dumps(summary(index), indent=2))
            for finding in findings:
                print(finding)
            print(f"\n{len(findings)} dangling reference(s).")
        return 1 if findings else 0

    sites = impact(index, name=args.name, path=args.path)
    if args.json:
        print(json.dumps([s.as_dict() for s in sites], indent=2))
    else:
        for site in sites:
            print(site)
        print(f"\n{len(sites)} site(s) refer to {args.name or args.path}.")
    return 0 if sites else 1


if __name__ == "__main__":
    raise SystemExit(main())
