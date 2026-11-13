#!/usr/bin/env python3
"""Fact-check agent: verify a script's factual claims against live web research.

This is not a scientific-dossier requirement. Its job is to catch false, fake, or
unsupported factual claims in a video script before the video is rendered or
published. Fiction (invented stories, novels, narrative skits) is exempt: there is
nothing to fact-check in an invented world, so the gate returns ``exempt`` without
touching the network.

For factual content each checkable claim is searched on the live web through the
Exa search API. A claim is ``corroborated`` only when a retrieved source actually
contains its spoken numbers (and a named entity when the claim names one); anything
else is ``unverified`` and flagged for human review. The agent never invents a
source, never asserts a claim is true without a retrieved citation, and never
silently downgrades to an offline guess: a missing API key raises with the fix.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

TOOLS_DIR = Path(__file__).resolve().parent
YT_ROOT = TOOLS_DIR.parent
if str(YT_ROOT) not in sys.path:
    sys.path.insert(0, str(YT_ROOT))

from tools.schemas import CONTENT_TYPES, DEFAULT_CONTENT_TYPE  # noqa: E402

EXA_SEARCH_URL = "https://api.exa.ai/search"
EXA_API_KEY_ENV = "EXA_API_KEY"

# A spoken number, including ordinals and decimal/grouped values (mirrors verify_script).
_NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:,\d{3})*(?:\.\d+)?(?:st|nd|rd|th)?", re.IGNORECASE)
_ENTITY_RE = re.compile(r"\b[A-Z][a-zA-Z]{2,}\b")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
# Markers that turn a sentence into a checkable factual assertion rather than narration.
_STUDY_TERMS = (
    "study", "studies", "research", "researchers", "experiment", "university",
    "published", "survey", "scientists", "according to", "percent", "statistics",
)
_ENTITY_STOPWORDS = frozenset({
    "The", "This", "That", "These", "Those", "Your", "You", "But", "And", "When",
    "Why", "How", "What", "Here", "There", "Ever", "Stop", "Let", "Its", "Our",
})


class FactCheckError(RuntimeError):
    """Raised when fact-checking cannot run; the message carries the fix command."""


def normalize_content_type(value: object) -> str:
    text = str(value if value is not None else DEFAULT_CONTENT_TYPE).strip().lower()
    if text not in CONTENT_TYPES:
        raise FactCheckError(f"content_type must be one of {sorted(CONTENT_TYPES)}, got {value!r}.")
    return text


def _numeric_tokens(text: str) -> set[str]:
    return {
        re.sub(r"(?:st|nd|rd|th)$", "", token.lower().replace(",", ""))
        for token in _NUMBER_RE.findall(text)
    }


def _entities(text: str) -> list[str]:
    return sorted({m for m in _ENTITY_RE.findall(text) if m not in _ENTITY_STOPWORDS})


def extract_claims(scenes: list[dict]) -> list[dict]:
    """Pull checkable factual assertions from scene narration.

    A sentence is checkable when it carries a spoken number or a research/statistic
    marker. Pure narration and opinion are left alone.
    """
    claims: list[dict] = []
    for index, scene in enumerate(scenes, 1):
        text = str(scene.get("text", "")).strip()
        if not text:
            continue
        for sentence in _SENTENCE_SPLIT.split(text):
            sentence = sentence.strip()
            if not sentence:
                continue
            numbers = sorted(_numeric_tokens(sentence))
            lowered = sentence.lower()
            terms = [term for term in _STUDY_TERMS if term in lowered]
            if not numbers and not terms:
                continue
            claims.append({
                "scene": index,
                "text": sentence,
                "numbers": numbers,
                "entities": _entities(sentence),
                "terms": terms,
            })
    return claims


def _exa_search(query: str, *, api_key: str, num_results: int = 5) -> list[dict]:
    """Query the live Exa search API. Raises FactCheckError on any failure (no fallback)."""
    body = json.dumps({
        "query": query,
        "numResults": num_results,
        "contents": {"text": True},
    }).encode("utf-8")
    request = urllib.request.Request(
        EXA_SEARCH_URL,
        data=body,
        headers={"x-api-key": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
        raise FactCheckError(f"Exa search failed for {query!r}: {exc}. Check network and {EXA_API_KEY_ENV}.") from exc
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise FactCheckError(f"Exa search returned no results list for {query!r}.")
    sources = []
    for item in results:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "")
        if not url.startswith("https://"):
            continue
        sources.append({
            "title": str(item.get("title") or ""),
            "url": url,
            "text": str(item.get("text") or ""),
        })
    return sources


def _corroborates(claim: dict, source: dict) -> bool:
    """A source corroborates a claim only if it contains every spoken number and,
    when the claim names an entity, at least one of those entities. No numbers and
    no entity means nothing concrete to match, so it cannot auto-corroborate."""
    haystack = f"{source.get('title', '')} {source.get('text', '')}".lower()
    numbers = claim.get("numbers") or []
    entities = claim.get("entities") or []
    if not numbers and not entities:
        return False
    if not all(number in haystack for number in numbers):
        return False
    if entities and not any(entity.lower() in haystack for entity in entities):
        return False
    return True


def _resolve_search(
    search_fn: Callable[..., list[dict]] | None, api_key: str | None
) -> Callable[[str], list[dict]]:
    if search_fn is not None:
        return lambda query: search_fn(query)
    key = api_key if api_key is not None else os.environ.get(EXA_API_KEY_ENV, "")
    if not key:
        raise FactCheckError(
            f"Factual fact-checking needs live web research, but {EXA_API_KEY_ENV} is not set. "
            f"Export it (export {EXA_API_KEY_ENV}=<your key>) or mark the video content_type=fiction. "
            "There is no offline fallback: an unverified factual claim must not pass silently."
        )
    return lambda query: _exa_search(query, api_key=key)


def exempt_report(content_type: str = "fiction") -> dict:
    return {
        "content_type": normalize_content_type(content_type),
        "status": "exempt",
        "passed": True,
        "checked": 0,
        "claims": [],
        "flags": [],
        "note": "Fiction is exempt from fact-checking; no factual claims are asserted.",
    }


def dossier_report() -> dict:
    """A verified scientific dossier already satisfies the factual research gate."""
    return {
        "content_type": "factual",
        "status": "satisfied_by_dossier",
        "passed": True,
        "checked": 0,
        "claims": [],
        "flags": [],
        "note": "Factual claims are grounded in a verified primary-source dossier.",
    }


def check_script(
    scenes: list[dict],
    *,
    content_type: str = DEFAULT_CONTENT_TYPE,
    search_fn: Callable[..., list[dict]] | None = None,
    api_key: str | None = None,
) -> dict:
    """Fact-check a script. Fiction returns exempt; factual claims are searched live."""
    kind = normalize_content_type(content_type)
    if kind == "fiction":
        return exempt_report("fiction")

    claims = extract_claims(scenes)
    if not claims:
        return {
            "content_type": "factual",
            "status": "passed",
            "passed": True,
            "checked": 0,
            "claims": [],
            "flags": [],
            "note": "No checkable factual claims in the script.",
        }

    search = _resolve_search(search_fn, api_key)
    checked: list[dict] = []
    flags: list[str] = []
    for claim in claims:
        sources = search(claim["text"])
        corroborating = [s for s in sources if _corroborates(claim, s)]
        verdict = "corroborated" if corroborating else "unverified"
        record = {
            "scene": claim["scene"],
            "text": claim["text"],
            "numbers": claim["numbers"],
            "entities": claim["entities"],
            "verdict": verdict,
            "sources": [{"title": s["title"], "url": s["url"]} for s in (corroborating or sources)[:3]],
        }
        checked.append(record)
        if verdict != "corroborated":
            flags.append(f"scene {claim['scene']}: {claim['text']}")
    return {
        "content_type": "factual",
        "status": "passed" if not flags else "flagged",
        "passed": not flags,
        "checked": len(checked),
        "claims": checked,
        "flags": flags,
        "note": (
            "All factual claims corroborated by live web sources."
            if not flags
            else f"{len(flags)} claim(s) unverified by live web research; review before publishing."
        ),
    }


def check_project(
    project: dict,
    *,
    search_fn: Callable[..., list[dict]] | None = None,
    api_key: str | None = None,
) -> dict:
    """Fact-check a project dict using its content_type and scene narration."""
    if not isinstance(project, dict):
        raise FactCheckError("project must be an object")
    scenes = project.get("scenes")
    if not isinstance(scenes, list):
        raise FactCheckError("project.scenes must be a list")
    return check_script(
        scenes,
        content_type=project.get("content_type", DEFAULT_CONTENT_TYPE),
        search_fn=search_fn,
        api_key=api_key,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fact-check a video script against live web research.")
    parser.add_argument("--project", required=True, help="Path to project.json")
    parser.add_argument("--content-type", choices=sorted(CONTENT_TYPES), default=None,
                        help="Override the project's content_type")
    parser.add_argument("--output", help="Write the JSON report here (default: beside project.json)")
    parser.add_argument("--json", action="store_true", help="Print the JSON report")
    args = parser.parse_args(argv)

    project_path = Path(args.project)
    try:
        project = json.loads(project_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"Cannot read project: {exc}", file=sys.stderr)
        return 2
    if args.content_type:
        project["content_type"] = args.content_type
    try:
        report = check_project(project)
    except FactCheckError as exc:
        print(f"Fact-check could not run: {exc}", file=sys.stderr)
        return 2

    output = Path(args.output) if args.output else project_path.parent / "fact_check.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Fact-check: {report['status']} ({report['checked']} claim(s) checked)")
        for flag in report["flags"]:
            print(f"  ! unverified: {flag}")
        print(f"Report: {output}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())