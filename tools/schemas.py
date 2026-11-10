"""Small runtime contracts for authored projects and release evidence.

These checks intentionally use plain dictionaries rather than a schema package so the
release boundary stays available in the minimal production environment.  They return
all independent errors in one pass; callers decide whether an error is fatal.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from tools.atomic_files import durable_write_text

SCHEMA_VERSION = 1
_ID_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*\Z")
_HASH_RE = re.compile(r"[0-9a-f]{64}\Z")


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _valid_id(value: object) -> bool:
    return isinstance(value, str) and bool(_ID_RE.fullmatch(value))


def _safe_relative_path(value: object, *, project_path: Path | None) -> bool:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        return False
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts or "://" in value:
        return False
    if project_path is not None:
        root = project_path.parent.resolve()
        try:
            (root / candidate).resolve().relative_to(root)
        except ValueError:
            return False
    return True


def validate_project(data: dict, *, project_path: Path | None = None) -> list[str]:
    """Return every actionable authored-project contract error.

    A missing version/format remains compatible for legacy build inputs.  New project
    writers emit both fields, while strict evidence has its own non-legacy contract.
    """
    if not isinstance(data, dict):
        return ["project must be an object"]
    errors: list[str] = []
    version = data.get("schema_version")
    if version is not None and version != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if not _valid_id(data.get("id")):
        errors.append("id must be a safe video identifier")
    fmt = data.get("format", "short")
    if fmt not in {"short", "long"}:
        errors.append("format must be 'short' or 'long'")

    scenes = data.get("scenes")
    if not isinstance(scenes, list):
        errors.append("scenes must be a list")
        scenes = []
    elif not 8 <= len(scenes) <= 12:
        errors.append("scenes must contain 8-12 entries")
    scene_ids: set[str] = set()
    for index, scene in enumerate(scenes):
        label = f"scenes[{index}]"
        if not isinstance(scene, dict):
            errors.append(f"{label} must be an object")
            continue
        scene_id = scene.get("id")
        if scene_id is not None:
            if not _valid_id(scene_id):
                errors.append(f"{label}.id must be a safe scene identifier")
            elif scene_id in scene_ids:
                errors.append(f"{label}.id duplicates an earlier scene")
            else:
                scene_ids.add(scene_id)
        for field in ("text", "prompt"):
            if not isinstance(scene.get(field), str) or not scene[field].strip():
                errors.append(f"{label}.{field} must be a non-empty string")
        for field in ("image", "video", "audio"):
            if field in scene and not _safe_relative_path(scene[field], project_path=project_path):
                errors.append(f"{label}.{field} must stay inside the project directory")
        for field in ("shots", "images"):
            if field not in scene:
                continue
            specs = scene[field]
            if not isinstance(specs, list):
                errors.append(f"{label}.{field} must be a list of media paths or objects")
                continue
            for spec_index, spec in enumerate(specs):
                spec_label = f"{label}.{field}[{spec_index}]"
                if isinstance(spec, str):
                    if not _safe_relative_path(spec, project_path=project_path):
                        errors.append(f"{spec_label} must stay inside the project directory")
                elif isinstance(spec, dict):
                    for media_field in ("image", "video"):
                        if media_field in spec and not _safe_relative_path(spec[media_field], project_path=project_path):
                            errors.append(f"{spec_label}.{media_field} must stay inside the project directory")
                else:
                    errors.append(f"{spec_label} must be a media path or object")

    music = data.get("music")
    if music is not None:
        if not isinstance(music, dict):
            errors.append("music must be an object")
        else:
            for field in ("volume", "sfx_volume"):
                if field in music and (not _is_number(music[field]) or not 0 <= music[field] <= 1):
                    errors.append(f"music.{field} must be a number between 0 and 1")
            for field in ("bpm", "seed"):
                if field in music and (not isinstance(music[field], int) or isinstance(music[field], bool)):
                    errors.append(f"music.{field} must be an integer")
    for field in ("gap", "tail"):
        if field in data and (not _is_number(data[field]) or data[field] < 0):
            errors.append(f"{field} must be a non-negative number")
    for field in ("rate", "pitch"):
        if field in data and not isinstance(data[field], str):
            errors.append(f"{field} must be a string")
    if "progress_bar" in data and not isinstance(data["progress_bar"], bool):
        errors.append("progress_bar must be a boolean")
    if "evidence_bundle" in data and not _safe_relative_path(data["evidence_bundle"], project_path=project_path):
        errors.append("evidence_bundle must stay inside the project directory")
    return errors


def _scene_reference_ok(value: object, scene_count: int | None) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    match = re.fullmatch(r"scene_(\d+)(?:_[a-z_]+)?", value)
    return match is None or scene_count is None or 1 <= int(match.group(1)) <= scene_count


def validate_evidence(
    data: dict,
    *,
    project: dict | None = None,
    evidence_path: Path | None = None,
) -> list[str]:
    """Return strict evidence errors, including human-review and project binding checks."""
    if not isinstance(data, dict):
        return ["evidence must be an object"]
    errors: list[str] = []
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if data.get("status") != "reviewed":
        errors.append("status is unreviewed; reviewed evidence is required")
    if not _valid_id(data.get("video_id")):
        errors.append("video_id must be a safe video identifier")

    source = data.get("primary_source")
    if not isinstance(source, dict):
        errors.append("primary_source must be an object")
    else:
        for field in ("title", "publication"):
            if not isinstance(source.get(field), str) or not source[field].strip():
                errors.append(f"primary_source.{field} must be a non-empty string")
        authors = source.get("authors")
        if not isinstance(authors, list) or not authors or not all(isinstance(a, str) and a.strip() for a in authors):
            errors.append("primary_source.authors must be a non-empty list of names")
        if not re.fullmatch(r"\d{4}", str(source.get("year", ""))):
            errors.append("primary_source.year must be four digits")
        if not isinstance(source.get("url"), str) or not re.fullmatch(r"https://[^/\s]+(?:/[^\s]*)?", source["url"]):
            errors.append("primary_source.url must be an HTTPS URL")

    scene_count = len(project["scenes"]) if isinstance(project, dict) and isinstance(project.get("scenes"), list) else None
    claims = data.get("claims")
    claim_ids: set[str] = set()
    if not isinstance(claims, list) or not claims:
        errors.append("claims must be a non-empty list")
        claims = []
    for index, claim in enumerate(claims):
        label = f"claims[{index}]"
        if not isinstance(claim, dict):
            errors.append(f"{label} must be an object")
            continue
        claim_id = claim.get("id")
        if not _valid_id(claim_id):
            errors.append(f"{label}.id must be a safe claim identifier")
        elif claim_id in claim_ids:
            errors.append(f"{label}.id duplicates an earlier claim")
        else:
            claim_ids.add(claim_id)
        for field in ("paraphrase", "printed_page_locator", "support_summary"):
            if not isinstance(claim.get(field), str) or not claim[field].strip():
                errors.append(f"{label}.{field} must be a non-empty string")
        uses = claim.get("used_by")
        if not isinstance(uses, list) or not uses or not all(_scene_reference_ok(item, scene_count) for item in uses):
            errors.append(f"{label}.used_by must reference valid scenes")

    editorial = data.get("editorial_suggestions")
    if not isinstance(editorial, list) or not editorial:
        errors.append("editorial_suggestions must be a non-empty list")
        editorial = []
    editorial_ids: set[str] = set()
    for index, item in enumerate(editorial):
        label = f"editorial_suggestions[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        item_id = item.get("id")
        if not _valid_id(item_id) or item_id in claim_ids or item_id in editorial_ids:
            errors.append(f"{label}.id must be unique and distinct from claims")
        else:
            editorial_ids.add(item_id)
        for field in ("text", "status"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append(f"{label}.{field} must be a non-empty string")
        if "paraphrase" in item:
            errors.append(f"{label}.paraphrase belongs only to factual claims")
        uses = item.get("used_by")
        if not isinstance(uses, list) or not uses or not all(_scene_reference_ok(value, scene_count) for value in uses):
            errors.append(f"{label}.used_by must reference valid scenes")

    digest = data.get("script_sha256")
    if not isinstance(digest, str) or not _HASH_RE.fullmatch(digest):
        errors.append("script_sha256 must be a SHA-256 digest")
    if isinstance(project, dict):
        if data.get("video_id") != project.get("id"):
            errors.append("video_id must match project.id")
        if isinstance(project.get("scenes"), list):
            script = "\n".join(str(scene.get("text", "")) for scene in project["scenes"] if isinstance(scene, dict))
            if digest != hashlib.sha256(script.encode("utf-8")).hexdigest():
                errors.append("script_sha256 must match project scene text")
        if project.get("citation_verified") is not True:
            errors.append("citation_verified must be true on the bound project")
        if project.get("contains_synthetic_media") is not True:
            errors.append("contains_synthetic_media must be true on the bound project")
        bundle = project.get("evidence_bundle")
        if not _safe_relative_path(bundle, project_path=None):
            errors.append("evidence_bundle must bind the evidence file")
        elif evidence_path is not None and Path(bundle).name != evidence_path.name:
            errors.append("evidence_bundle must name the bound evidence file")
    return errors


def prepare_release_draft(project_path: Path, output_path: Path, dossier: dict | None = None) -> Path:
    """Write an unreviewed evidence draft without changing the source project."""
    project_path = Path(project_path)
    output_path = Path(output_path)
    try:
        project = json.loads(project_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read project: {exc}") from exc
    errors = validate_project(project, project_path=project_path)
    if errors:
        raise ValueError("\n".join(errors))
    if output_path.exists() or output_path.resolve() == project_path.resolve():
        raise ValueError("refusing to overwrite a project or existing evidence file")
    source_data = dossier if isinstance(dossier, dict) else {}
    source = source_data.get("primary_source") if isinstance(source_data.get("primary_source"), dict) else source_data
    primary_source = {
        "title": source.get("title", "") if isinstance(source.get("title", ""), str) else "",
        "authors": source.get("authors", []) if isinstance(source.get("authors", []), list) else [],
        "year": source.get("year", ""),
        "publication": source.get("publication", "") if isinstance(source.get("publication", ""), str) else "",
        "url": source.get("url", "") if isinstance(source.get("url", ""), str) else "",
    }
    claims = []
    for claim in project.get("claims", []) if isinstance(project.get("claims"), list) else []:
        if isinstance(claim, dict):
            claims.append({
                **{key: claim[key] for key in ("id", "paraphrase", "used_by") if key in claim},
                "printed_page_locator": claim.get("printed_page_locator", ""),
                "support_summary": claim.get("support_summary", ""),
            })
    editorial = []
    for item in project.get("editorial_suggestions", []) if isinstance(project.get("editorial_suggestions"), list) else []:
        if isinstance(item, dict):
            editorial.append({**item, "status": item.get("status", "")})
    script = "\n".join(str(scene.get("text", "")) for scene in project["scenes"])
    draft: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "draft",
        "video_id": project["id"],
        "primary_source": primary_source,
        "claims": claims,
        "editorial_suggestions": editorial,
        "script_sha256": hashlib.sha256(script.encode("utf-8")).hexdigest(),
    }
    if source_data:
        draft["dossier"] = source_data
    durable_write_text(output_path, json.dumps(draft, indent=2) + "\n")
    return output_path
