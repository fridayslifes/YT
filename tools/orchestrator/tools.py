"""Read-only, root-scoped tools available to the master and workers."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

SKIP_DIRS = {
    ".git",
    ".venv",
    ".orchestrator",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "models",
    "node_modules",
    "kokoro_models",
}
MAX_READ_BYTES = 300_000
MAX_OUTPUT_CHARS = 12_000


class ToolError(RuntimeError):
    pass


class ProjectTools:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def _safe_path(self, path: str | Path) -> Path:
        candidate = Path(path)
        resolved = candidate.resolve() if candidate.is_absolute() else (self.root / candidate).resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise ToolError(f"path escapes project root: {path}")
        return resolved

    def _rg(self) -> str | None:
        return shutil.which("rg")

    def search_code(
        self,
        query: str,
        *,
        glob: str | None = None,
        context: int = 1,
        max_results: int = 40,
    ) -> dict:
        if not query.strip():
            raise ToolError("empty search query")
        rg = self._rg()
        if rg:
            argv = [
                rg,
                "--line-number",
                "--no-heading",
                "--color",
                "never",
                "--max-count",
                "8",
                "--context",
                str(max(0, context)),
                "--max-filesize",
                "2M",
            ]
            for skip in sorted(SKIP_DIRS):
                argv.extend(["--glob", f"!{skip}/**"])
            if glob:
                argv.extend(["--glob", glob])
            argv.extend(["--", query])
        else:
            argv = ["grep", "-RIn", "--exclude-dir", ".venv", "--exclude-dir", ".git", query, "."]
        proc = subprocess.run(
            argv,
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        matches: list[dict] = []
        for raw in proc.stdout.splitlines():
            line = raw.rstrip()
            if len(line) > 320:
                line = line[:317] + "..."
            first, sep, rest = line.partition(":")
            if not sep or not rest:
                continue
            lineno, sep2, text = rest.partition(":")
            if not sep2 or not lineno.isdigit():
                continue
            matches.append({"path": first, "line": int(lineno), "text": text.strip()})
            if len(matches) >= max_results:
                break
        return {
            "query": query,
            "engine": "rg" if rg else "grep",
            "returncode": proc.returncode,
            "matches": matches,
            "truncated": len(matches) >= max_results,
        }

    def read_file(self, path: str | Path, *, offset: int = 1, limit: int = 200) -> dict:
        target = self._safe_path(path)
        if not target.is_file():
            raise ToolError(f"not a file: {path}")
        size = target.stat().st_size
        if size > MAX_READ_BYTES:
            raise ToolError(f"file too large to read safely ({size} bytes): {path}")
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(0, offset - 1)
        selected = lines[start : start + limit]
        return {
            "path": str(target.relative_to(self.root)),
            "total_lines": len(lines),
            "offset": start + 1,
            "lines": [{"n": start + i + 1, "text": text} for i, text in enumerate(selected)],
        }

    def list_files(self, path: str = ".", *, pattern: str = "**/*", limit: int = 300) -> list[str]:
        base = self._safe_path(path)
        items: list[str] = []
        for p in sorted(base.glob(pattern)):
            if not p.is_file():
                continue
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            items.append(str(p.relative_to(self.root)))
            if len(items) >= limit:
                break
        return items

    def run_command(self, argv: Iterable[str], *, timeout: int = 120) -> dict:
        args = [str(a) for a in argv]
        if not args:
            raise ToolError("empty command")
        exe = Path(args[0]).name
        allowed = {"rg", "ffprobe", "ffmpeg", "ls", "stat", "wc", "du", "git"}
        if exe not in allowed:
            raise ToolError(f"command not allowed: {exe}")
        if exe == "git":
            sub = args[1] if len(args) > 1 else ""
            if sub not in {"status", "log", "diff", "show", "rev-parse"}:
                raise ToolError(f"git subcommand not allowed: {sub}")
        proc = subprocess.run(
            args,
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=max(5, min(timeout, 600)),
        )
        return {
            "argv": args,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-MAX_OUTPUT_CHARS:],
            "stderr": proc.stderr[-4000:],
        }

    def git_status(self) -> dict:
        try:
            return self.run_command(["git", "status", "--short"])
        except Exception as exc:  # noqa: BLE001
            return {"returncode": -1, "stdout": "", "stderr": str(exc)}

    def json_summary(self, path: str | Path, *, keys: list[str] | None = None) -> dict:
        target = self._safe_path(path)
        data = json.loads(target.read_text(encoding="utf-8"))
        if keys:
            data = {k: data.get(k) for k in keys}
        return data
