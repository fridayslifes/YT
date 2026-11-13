"""Independent verification gates. A worker's own success claim is never trusted."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Callable

from tools.output_format import VOICE_BLACKLIST
from tools.schemas import validate_evidence, validate_project

from .contracts import CheckResult, TaskSpec, WorkerResult
from .state import RunContext

VERIFIERS: dict[str, Callable[[TaskSpec, WorkerResult, RunContext], list[CheckResult]]] = {}

def verifier(name: str):
    def decorate(fn):
        VERIFIERS[name] = fn
        return fn

    return decorate


def _check(
    name: str,
    passed: bool,
    message: str,
    *,
    severity: str = "critical",
    metrics: dict | None = None,
) -> CheckResult:
    return CheckResult(
        name=name,
        passed=bool(passed),
        severity=severity,
        message=message,
        metrics=metrics or {},
    )


def _resolve(ctx: RunContext, value: str | Path | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else ctx.project_root / path


def _project_json(ctx: RunContext, result: WorkerResult | None = None) -> Path | None:
    current = _resolve(ctx, result.artifacts.get("project_json")) if result else None
    if current and current.exists():
        return current
    direct = ctx.project_json()
    if direct and direct.exists():
        return direct
    for record in ctx.state.tasks.values():
        value = record.artifacts.get("project_json")
        path = _resolve(ctx, value)
        if path and path.exists():
            return path
    return None


def _project_from_ctx(ctx: RunContext) -> Path | None:
    project_json = _project_json(ctx)
    return project_json.parent if project_json else None


def _mp4_from_ctx(ctx: RunContext) -> Path | None:
    for task_id in ("build", "release", "qa"):
        path = _resolve(ctx, ctx.artifact(task_id, "output_mp4"))
        if path and path.exists():
            return path
    project = _project_from_ctx(ctx)
    if project:
        expected = project / "output" / f"{project.name}.mp4"
        if expected.exists():
            return expected
    return None


def _kit_from_ctx(ctx: RunContext, result: WorkerResult | None = None) -> Path | None:
    current = _resolve(ctx, result.artifacts.get("upload_kit")) if result else None
    if current and current.is_file():
        return current
    project_json = _project_json(ctx, result)
    project = project_json.parent if project_json else None
    if project:
        kits = sorted(project.glob("UPLOAD_KIT*.md"))
        if kits:
            return kits[0]
    return None


def artifact_integrity(result: WorkerResult, ctx: RunContext) -> list[CheckResult]:
    checks: list[CheckResult] = []
    if not result.artifacts:
        return checks
    for name, value in result.artifacts.items():
        if not value or str(value).startswith(("http://", "https://")):
            continue
        path = _resolve(ctx, value)
        if path is None or not path.exists():
            checks.append(
                _check(
                    f"artifact:{name}",
                    False,
                    f"worker reported artifact '{name}' but it does not exist: {value}",
                )
            )
        elif path.is_file() and path.stat().st_size == 0:
            checks.append(
                _check(f"artifact:{name}", False, f"artifact '{name}' is empty: {value}")
            )
    if checks:
        return checks
    return [_check("artifact_integrity", True, f"{len(result.artifacts)} artifact(s) verified")]


def _read_strict_inputs(spec: TaskSpec, ctx: RunContext) -> tuple[dict, dict]:
    evidence_path = _resolve(ctx, spec.params.get("evidence"))
    project_path = _resolve(ctx, spec.params.get("project_json"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    project = json.loads(project_path.read_text(encoding="utf-8"))
    if not isinstance(evidence, dict) or not isinstance(project, dict):
        raise ValueError("evidence and project must be objects")
    return evidence, project


def _strict_evidence_checks(spec: TaskSpec, result: WorkerResult, ctx: RunContext) -> list[CheckResult]:
    """Read the evidence and project independently, rather than trust worker data."""
    evidence_path = _resolve(ctx, spec.params.get("evidence"))
    project_path = _resolve(ctx, spec.params.get("project_json"))
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        project = json.loads(project_path.read_text(encoding="utf-8"))
        if not isinstance(evidence, dict) or not isinstance(project, dict):
            raise ValueError("evidence and project must be objects")
    except (OSError, ValueError, AttributeError, TypeError) as exc:
        return [_check("evidence_read", False, f"cannot read bound evidence/project: {exc}")]
    checks = []
    project_errors = validate_project(project, project_path=project_path)
    evidence_errors = validate_evidence(evidence, project=project, evidence_path=evidence_path)
    checks.extend(
        _check("project_schema", False, error) for error in project_errors
    )
    checks.extend(
        _check("evidence_schema", False, error) for error in evidence_errors
    )
    checks.append(
        _check(
            "evidence_video_id",
            bool(project.get("id")) and evidence.get("video_id") == project.get("id") == spec.params.get("video_id"),
            "evidence, project and release IDs must match",
        )
    )
    source = evidence.get("primary_source") or {}
    valid_source = (
        isinstance(source, dict)
        and all(isinstance(source.get(key), str) and source[key].strip() for key in ("title", "publication"))
        and isinstance(source.get("authors"), list)
        and bool(source["authors"])
        and all(isinstance(author, str) and author.strip() for author in source["authors"])
        and bool(re.fullmatch(r"\d{4}", str(source.get("year", ""))))
        and bool(re.match(r"https://[^/\s]+(?:/[^\s]*)?$", str(source.get("url", ""))))
    )
    checks.append(
        _check(
            "evidence_primary_source",
            valid_source,
            "primary source requires title, authors, year, publication and HTTPS URL",
        )
    )
    scenes = project.get("scenes") or []
    claims = evidence.get("claims") or []
    valid_claims = isinstance(claims, list) and bool(claims)
    ids = []
    for claim in claims if isinstance(claims, list) else []:
        if not isinstance(claim, dict):
            valid_claims = False
            continue
        ids.append(claim.get("id"))
        valid_claims = valid_claims and all(
            isinstance(claim.get(key), str) and bool(claim[key].strip())
            for key in ("id", "paraphrase", "printed_page_locator", "support_summary")
        )
        uses = claim.get("used_by")
        valid_claims = valid_claims and isinstance(uses, list) and bool(uses)
        for use in uses if isinstance(uses, list) else []:
            if not isinstance(use, str) or not use.strip():
                valid_claims = False
            elif use.startswith("scene_"):
                match = re.fullmatch(r"scene_(\d+)(?:_[a-z_]+)?", use)
                if not match or not 1 <= int(match.group(1)) <= len(scenes):
                    valid_claims = False
    unique = all(isinstance(value, str) for value in ids) and len(set(str(value) for value in ids)) == len(ids)
    checks.append(
        _check(
            "evidence_claims",
            valid_claims and unique,
            "claims require unique IDs, paraphrases, printed-page locators, support summaries and valid scene references",
        )
    )
    editorial = evidence.get("editorial_suggestions")
    valid_editorial = (
        isinstance(editorial, list)
        and bool(editorial)
        and all(
            isinstance(item, dict)
            and isinstance(item.get("text"), str)
            and bool(item["text"].strip())
            and bool(item.get("status"))
            and bool(item.get("used_by"))
            and item.get("id") not in ids
            and "paraphrase" not in item
            for item in editorial
        )
    )
    checks.append(
        _check(
            "evidence_editorial",
            valid_editorial,
            "editorial suggestions must be present and distinct from factual claims",
        )
    )
    script = "\n".join(str(scene.get("text", "")) for scene in scenes)
    digest = hashlib.sha256(script.encode("utf-8")).hexdigest()
    checks.append(
        _check(
            "evidence_script_sha256",
            evidence.get("script_sha256") == digest,
            "ordered scene text must match evidence script SHA-256",
        )
    )
    bound_path = _resolve(ctx, project.get("evidence_bundle"))
    checks.append(
        _check(
            "evidence_project_binding",
            project.get("citation_verified") is True
            and project.get("contains_synthetic_media") is True
            and bound_path is not None
            and bound_path.resolve() == evidence_path.resolve(),
            "project must bind this evidence bundle and declare verified citations and synthetic media",
        )
    )
    return checks


@verifier("research")
def verify_research(spec: TaskSpec, result: WorkerResult, ctx: RunContext) -> list[CheckResult]:
    content_type = str(
        spec.params.get("content_type") or result.data.get("content_type") or "factual"
    ).strip().lower()
    if content_type == "fiction":
        return [_check("research_fiction_exempt", True, "fiction: no dossier or fact-check required")]
    dossier = result.data.get("dossier") or {}
    strict_checks: list[CheckResult] = []
    if spec.params.get("strict_evidence"):
        try:
            evidence, _ = _read_strict_inputs(spec, ctx)
            dossier = evidence.get("dossier") or {}
            if not isinstance(dossier, dict):
                raise ValueError("dossier must be an object")
            strict_checks = _strict_evidence_checks(spec, result, ctx)
        except (OSError, ValueError, AttributeError, TypeError) as exc:
            return [_check("evidence_read", False, str(exc))]
    if not dossier:
        return strict_checks + [
            _check(
                "research_worker",
                False,
                result.error or result.summary or "no dossier returned",
            )
        ]
    if not isinstance(dossier, dict):
        return [_check("dossier_required_fields", False, "dossier must be an object")]
    required = [
        "topic",
        "primary_researchers",
        "year",
        "publication",
        "experiment_design",
        "quantitative_stat",
    ]
    missing = [key for key in required if dossier.get(key) is None or not str(dossier.get(key, "")).strip()]
    checks = [
        _check(
            "dossier_required_fields",
            not missing,
            "dossier has all required fields" if not missing else f"missing dossier fields: {missing}",
            metrics={"missing": missing},
        )
    ]
    researchers = str(dossier.get("primary_researchers", "")).lower()
    synthetic = dossier.get("_synthetic", False) is not False or "consortium" in researchers
    verified = dossier.get("_verified") is True
    checks.append(
        _check(
            "dossier_provenance",
            not synthetic and verified,
            "verified dossier"
            if verified and not synthetic
            else "unverified/synthetic dossier - add a real source before scripting",
            metrics={"source": dossier.get("_source", ""), "synthetic": synthetic},
        )
    )
    year = str(dossier.get("year", ""))
    checks.append(
        _check(
            "dossier_year",
            bool(re.fullmatch(r"(1[89]|20)\d{2}", year)),
            f"year is {year or 'missing'}",
        )
    )
    stat = str(dossier.get("quantitative_stat", ""))
    checks.append(
        _check(
            "dossier_stat",
            bool(re.search(r"\d", stat)),
            f"quantitative stat is {stat or 'missing'}",
        )
    )
    # method_claims can only compare the script to the dossier; it cannot tell whether the dossier
    # matches the paper. Three dossiers credited brain mechanisms to papers containing no scans, so
    # the source itself has to be recorded and reachable before a script is generated from it.
    src = dossier.get("primary_source")
    src_ok = (
        isinstance(src, dict)
        and isinstance(src.get("title"), str)
        and bool(src["title"].strip())
        and isinstance(src.get("authors"), list)
        and bool(src["authors"])
        and all(isinstance(a, str) and a.strip() for a in src["authors"])
        and bool(re.fullmatch(r"\d{4}", str(src.get("year", ""))))
        and bool(re.match(r"https://\S+", str(src.get("url", ""))))
    )
    checks.append(
        _check(
            "dossier_primary_source",
            src_ok,
            "dossier carries a checkable primary source"
            if src_ok
            else "dossier has no primary_source with title, authors, year and an HTTPS URL - "
                 "nothing to verify the mechanism line against",
        )
    )
    checks.extend(strict_checks)
    return checks


@verifier("factcheck")
def verify_factcheck(spec: TaskSpec, result: WorkerResult, ctx: RunContext) -> list[CheckResult]:
    """Read the written fact-check report independently; never trust the worker's claim.

    Offline-safe: this gate inspects the report artifact, it does not call the web.
    Fiction must be exempt; factual claims must be corroborated by a retrieved HTTPS
    source or grounded in a verified dossier, with zero unverified flags.
    """
    content_type = str(
        spec.params.get("content_type") or result.data.get("content_type") or "factual"
    ).strip().lower()
    report_path = _resolve(ctx, result.artifacts.get("fact_check"))
    if report_path is None or not report_path.exists():
        return [_check("factcheck_report", False, "fact_check.json missing")]
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [_check("factcheck_report", False, f"invalid fact_check.json: {exc}")]
    if not isinstance(report, dict):
        return [_check("factcheck_report", False, "fact-check report must be an object")]

    checks = [_check("factcheck_report", True, f"valid report: {report_path.name}")]
    status = report.get("status")
    if content_type == "fiction" or status == "exempt":
        checks.append(
            _check(
                "factcheck_fiction_exempt",
                status == "exempt" and content_type == "fiction",
                "fiction is exempt from fact-checking"
                if status == "exempt"
                else "exempt report is only valid for fiction",
            )
        )
        return checks

    checks.append(
        _check(
            "factcheck_status",
            status in {"passed", "satisfied_by_dossier"} and report.get("passed") is True,
            f"factual fact-check status={status}",
        )
    )
    flags = report.get("flags") or []
    checks.append(
        _check(
            "factcheck_no_flags",
            not flags,
            "no unverified factual claims" if not flags else f"unverified claims: {flags[:5]}",
            metrics={"flags": flags},
        )
    )
    bad: list[str] = []
    for claim in report.get("claims") or []:
        if not isinstance(claim, dict):
            bad.append("malformed claim")
            continue
        if claim.get("verdict") != "corroborated":
            bad.append(str(claim.get("text", ""))[:60])
            continue
        sources = claim.get("sources") or []
        if not any(isinstance(s, dict) and str(s.get("url", "")).startswith("https://") for s in sources):
            bad.append(f"no HTTPS source: {str(claim.get('text', ''))[:50]}")
    checks.append(
        _check(
            "factcheck_claim_sources",
            not bad,
            "every factual claim has a corroborating HTTPS source"
            if not bad
            else f"claims lacking corroboration: {bad[:5]}",
            metrics={"bad": bad},
        )
    )
    return checks


@verifier("script")
def verify_script(spec: TaskSpec, result: WorkerResult, ctx: RunContext) -> list[CheckResult]:
    from tools import youtube_skills
    from tools.policy import WORD_BANDS

    scenes = result.data.get("scenes") or []
    dossier = result.data.get("dossier") or {}
    evidence = {}
    if spec.params.get("strict_evidence"):
        try:
            evidence, project = _read_strict_inputs(spec, ctx)
            scenes = project.get("scenes") or []
            dossier = evidence.get("dossier") or {}
            if not isinstance(scenes, list) or not all(isinstance(scene, dict) for scene in scenes):
                raise ValueError("scenes must be a list of objects")
        except (OSError, ValueError, AttributeError, TypeError) as exc:
            return [_check("evidence_read", False, str(exc))]
    min_hook = int(spec.params.get("hook_min", youtube_skills.hookscore.STRONG_MIN))
    checks: list[CheckResult] = []
    checks.append(
        _check(
            "scene_count",
            8 <= len(scenes) <= 12,
            f"{len(scenes)} scenes (target 8-12)",
        )
    )
    texts = [str(sc.get("text", "")).strip() for sc in scenes]
    all_words = len(re.findall(r"\b\w+\b", " ".join(texts)))
    lo, hi = WORD_BANDS["short"]
    checks.append(
        _check(
            "word_count",
            lo <= all_words <= hi,
            f"{all_words} words (target {lo}-{hi})",
        )
    )
    missing_prompts = [i + 1 for i, sc in enumerate(scenes) if not str(sc.get("prompt", "")).strip()]
    checks.append(
        _check(
            "scene_prompts",
            not missing_prompts,
            "all scenes have visual prompts" if not missing_prompts else f"scenes missing prompts: {missing_prompts}",
        )
    )
    hook = texts[0] if texts else ""
    hook_res = youtube_skills.score_hook(hook) if hook else {"verdict": 0, "band": "MISSING", "weakest": ""}
    checks.append(
        _check(
            "hook_score",
            int(hook_res.get("verdict", 0)) >= min_hook,
            f"hook {hook_res.get('verdict')}/100 ({hook_res.get('band')}), weakest={hook_res.get('weakest')} (min {min_hook})",
            metrics={
                "score": hook_res.get("verdict"),
                "band": hook_res.get("band"),
                "weakest": hook_res.get("weakest"),
            },
        )
    )
    # Compare whole numeric tokens, including ordinals and decimal/grouped values.
    # Provenance paths and URLs cannot supply evidence for a spoken numeric claim.
    number_pattern = r"(?<![\w.])\d+(?:,\d{3})*(?:\.\d+)?(?:st|nd|rd|th)?"

    def numeric_tokens(text):
        return {
            re.sub(r"(?:st|nd|rd|th)$", "", token.lower().replace(",", ""))
            for token in re.findall(number_pattern, text, re.IGNORECASE)
        }

    factual_fields = (
        "topic", "year", "experiment_design", "quantitative_stat", "comparison_text",
        "broken_assumption", "biological_mechanism", "real_world_tax", "willpower_trap",
        "five_second_override", "best_hook", "loop_bridge",
    )
    # Source identifiers, URLs, page locators and unrelated metadata are not claims.
    # Restrict support to the dossier's narrative fields, stripping inline URLs too.
    dossier_text = " ".join(
        re.sub(r"\b(?:https?://|www\.)\S+", "", str(dossier[field]), flags=re.IGNORECASE)
        for field in factual_fields
        if isinstance(dossier.get(field), (str, int, float)) and not isinstance(dossier[field], bool)
    )
    dossier_numbers = numeric_tokens(dossier_text)
    unsourced: list[str] = []
    strict = bool(spec.params.get("strict_evidence"))
    supported_claims = evidence.get("claims", []) if strict else []
    for scene_num, text in enumerate(texts, 1):
        for token in re.findall(number_pattern, text, re.IGNORECASE):
            normalized = re.sub(r"(?:st|nd|rd|th)$", "", token.lower().replace(",", ""))
            if strict:
                supported = any(
                    isinstance(claim, dict)
                    and all(
                        str(claim.get(key, "")).strip()
                        for key in ("id", "paraphrase", "printed_page_locator", "support_summary")
                    )
                    and any(
                        re.fullmatch(rf"scene_{scene_num}(?:_[a-z_]+)?", str(use)) for use in claim.get("used_by", [])
                    )
                    and normalized in numeric_tokens(
                        " ".join(
                            str(claim.get(key, "")) for key in ("paraphrase", "support_summary")
                        )
                    )
                    for claim in supported_claims
                )
            else:
                supported = normalized in dossier_numbers
            if not supported:
                unsourced.append(token)
    checks.append(
        _check(
            "unsourced_numbers",
            not unsourced,
            "no numeric claims outside the dossier"
            if not unsourced
            else f"numeric claims not in dossier: {sorted(set(unsourced))}",
            metrics={"tokens": sorted(set(unsourced))},
        )
    )
    joined = " ".join(texts)
    banned = sorted(
        word for word in VOICE_BLACKLIST
        if re.search(r"\b" + re.escape(word) + r"\b", joined, re.IGNORECASE)
    )
    checks.append(
        _check(
            "voice_blacklist",
            not banned,
            "voice blacklist clean" if not banned else f"banned AI filler words: {banned}",
            severity="critical",
            metrics={"words": banned},
        )
    )
    # A spoken method or mechanism must appear in the dossier, on the same terms as a spoken number.
    # Brickman et al. (1978) interviewed lottery winners by telephone and face to face, yet the
    # scene-3 template prefixed every data line with "controlled laboratory testing" and the
    # dossier supplied a dopamine mechanism the paper never mentions. Both shipped in a render.
    method_terms = (
        "laborator", "experiment", "trial", "apparatus", "brain scan", "fmri", "pet scan",
        "amygdala", "insula", "dopamine", "accumbens", "receptor", "cortex", "glucose", "neuron",
        "synapt", "neurolog",
    )
    spoken = joined.lower()
    dossier_lower = dossier_text.lower()
    unsupported_methods = sorted(
        term
        for term in method_terms
        if re.search(rf"\b{term}", spoken) and not re.search(rf"\b{term}", dossier_lower)
    )
    checks.append(
        _check(
            "method_claims",
            not unsupported_methods,
            "no method or mechanism claim outside the dossier"
            if not unsupported_methods
            else f"script asserts {unsupported_methods} that the dossier never states",
            metrics={"terms": unsupported_methods},
        )
    )
    # The frame argues too. SH-17's narration was corrected to "interviewed" while its scene-4 image
    # prompt still asked FLUX for "prefrontal cortex and amygdala pathways" - a mechanism Brickman et
    # al. never measured - and scene 3 for a "laboratory testing table". A viewer reads a brain scan
    # as evidence, so the same rule that binds the spoken text must bind the rendered plates.
    visual = " ".join(str(sc.get("prompt", "")) for sc in scenes).lower()
    visual_methods = sorted(
        term
        for term in method_terms
        if re.search(rf"\b{term}", visual) and not re.search(rf"\b{term}", dossier_lower)
    )
    checks.append(
        _check(
            "visual_method_claims",
            not visual_methods,
            "no method or mechanism claim in the image prompts outside the dossier"
            if not visual_methods
            else f"image prompts depict {visual_methods} that the dossier never states",
            metrics={"terms": visual_methods},
        )
    )
    # A named living researcher in a generation prompt asks the model for that person's likeness,
    # which the FLUX Kommunity License s4.a(v) forbids when it violates publicity or "digital
    # replica" rights. Names belong in the citation overlay, not in the subject of the picture.
    researcher_names = [
        part.strip()
        for part in re.split(r"[,&]|\sand\s", str(dossier.get("primary_researchers", "")))
        if len(part.strip()) > 4
    ]
    named = [name for name in researcher_names if name.lower() in visual]
    checks.append(
        _check(
            "named_subject",
            not named,
            "no named researcher depicted in the image prompts"
            if not named
            else f"image prompts request a likeness of {named}; name them in the overlay instead",
            metrics={"names": named},
        )
    )
    claims = (evidence.get("claims") if strict else result.data.get("claims")) or []
    checks.append(
        _check(
            "claims_ledger",
            bool(claims),
            f"{len(claims)} claim(s) traced to dossier fields" if claims else "no claims ledger",
            metrics={"claims": claims},
        )
    )
    return checks


@verifier("direction")
def verify_direction(spec: TaskSpec, result: WorkerResult, ctx: RunContext) -> list[CheckResult]:
    manifest_path = _resolve(ctx, result.artifacts.get("director_manifest"))
    if not manifest_path or not manifest_path.exists():
        return [_check("direction_manifest", False, "director_manifest.json missing")]

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return [_check("direction_manifest", False, f"invalid director_manifest.json: {exc}")]

    checks: list[CheckResult] = [_check("direction_manifest", True, f"valid JSON: {manifest_path.name}")]
    scenes = manifest.get("scenes", [])
    scene_count = len(scenes)
    checks.append(
        _check(
            "direction_scenes",
            8 <= scene_count <= 12,
            f"{scene_count} scenes directed",
        )
    )

    all_spatial = all(
        isinstance(sc.get("spatial"), dict)
        and bool(sc["spatial"].get("character_position"))
        and bool(sc["spatial"].get("movement_vector"))
        for sc in scenes
    )
    checks.append(_check("direction_spatial", all_spatial, "character positions and movement vectors specified"))

    all_lighting = all(
        isinstance(sc.get("lighting"), dict)
        and bool(sc["lighting"].get("key_light_source"))
        and bool(sc["lighting"].get("dominant_side"))
        for sc in scenes
    )
    checks.append(_check("direction_lighting", all_lighting, "directional lighting and shadow dominance specified"))

    all_camera = all(
        isinstance(sc.get("camera"), dict)
        and bool(sc["camera"].get("trajectory_preset"))
        and 0.44 <= float(sc["camera"].get("safe_zone_anchor", 0.5)) <= 0.58
        for sc in scenes
    )
    checks.append(_check("direction_camera", all_camera, "3D camera trajectories and safe-zone anchors within band"))

    all_sound = all(
        isinstance(sc.get("sound"), dict)
        and bool(sc["sound"].get("score_movement"))
        and bool(sc["sound"].get("foley_cue"))
        for sc in scenes
    )
    checks.append(_check("direction_sound", all_sound, "score movement and word-aligned Foley sound cues specified"))

    pitch_path = _resolve(ctx, result.artifacts.get("director_pitch"))
    checks.append(
        _check(
            "direction_pitch",
            bool(pitch_path and pitch_path.exists()),
            "DIRECTOR_PITCH.md generated for review" if pitch_path and pitch_path.exists() else "missing DIRECTOR_PITCH.md",
        )
    )
    return checks


@verifier("project")
def verify_project(spec: TaskSpec, result: WorkerResult, ctx: RunContext) -> list[CheckResult]:
    path = _resolve(ctx, result.artifacts.get("project_json"))
    checks: list[CheckResult] = []
    if not path or not path.exists():
        return [_check("project_json", False, "project.json missing")]
    try:
        project = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return [_check("project_json", False, f"invalid project.json: {exc}")]
    checks.append(_check("project_json", True, f"valid JSON: {path.name}"))
    checks.extend(_check("project_schema", False, error) for error in validate_project(project, project_path=path))
    if not isinstance(project, dict):
        project = {}
    scenes = project.get("scenes")
    scene_count = len(scenes) if isinstance(scenes, list) else 0
    checks.append(
        _check(
            "project_scenes",
            8 <= scene_count <= 12,
            f"{scene_count} scenes",
        )
    )
    expected_id = str(spec.params.get("video_id", ""))
    checks.append(
        _check(
            "project_id",
            not expected_id or project.get("id") == expected_id,
            f"id={project.get('id')} expected={expected_id or 'any'}",
        )
    )
    # Burned-in text has one uncontested band on a Short: below the face our own 3D prompt frames
    # at 30-58% of height, above the Shorts UI block (~20-25% of the bottom). SH-18's scene 1 shipped
    # a caption at 0.34 - across the subject's mouth - and the hook card at 0.16, over the eyes.
    from tools.build_video import FORMATS, SHORT_TEXT_BAND

    band_lo, band_hi = SHORT_TEXT_BAND
    anchors: dict[str, list[float]] = {}
    if project.get("format") == "short":
        fmt = FORMATS["short"]
        anchors["cap_y"] = [float(sc.get("cap_y", fmt["cap_y"])) for sc in scenes if isinstance(sc, dict)]
        anchors.update({key: [float(fmt[key])] for key in ("overlay_y", "note_y", "stat_y")})
    off_band = {k: sorted({v for v in vals if not band_lo <= v <= band_hi}) for k, vals in anchors.items()}
    off_band = {k: v for k, v in off_band.items() if v}
    checks.append(
        _check(
            "caption_safe_band",
            not off_band,
            f"all burned-in text inside {band_lo}-{band_hi} of frame height"
            if not off_band
            else f"text anchors outside the Shorts safe band: {off_band}",
            severity="critical",
            metrics={"band": [band_lo, band_hi], "offenders": off_band},
        )
    )
    kits = sorted(path.parent.glob("UPLOAD_KIT*.md"))
    checks.append(
        _check(
            "upload_kit",
            bool(kits),
            f"upload kit: {kits[0].name}" if kits else "no UPLOAD_KIT_*.md",
        )
    )
    return checks


@verifier("packaging")
def verify_packaging(spec: TaskSpec, result: WorkerResult, ctx: RunContext) -> list[CheckResult]:
    from tools import youtube_skills

    kit = _kit_from_ctx(ctx, result)
    checks: list[CheckResult] = []
    if not kit:
        return [_check("upload_kit", False, "no upload kit found")]
    text = kit.read_text(encoding="utf-8", errors="replace")
    title_match = re.search(
        r"\*\*(?:Option\s+\d+:\s*)?Primary[^\*]*\*\*:\s*\n\s*>\s*`?([^`\n\r]+)`?",
        text,
    )
    title = title_match.group(1).strip() if title_match else ""
    if not title:
        title_match = re.search(r">\s*`?([^\r\n`]+#shorts)`?", text, re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else ""
    checks.append(_check("packaged_title", bool(title), f"title: {title or 'missing'}"))
    if title:
        checks.append(
            _check(
                "title_length",
                len(title) <= 60,
                f"{len(title)} characters",
                severity="critical" if spec.params.get("strict_release") or len(title) <= 60 else "warning",
            )
        )
        internal_id = re.search(r"\b(?:SH|LV)-\d+[A-Z]?\b|\bShort #\d+\b", title)
        checks.append(
            _check(
                "no_internal_id",
                not internal_id,
                "no production ID in public title"
                if not internal_id
                else f"production ID leaked into title: {internal_id.group(0)}",
                severity="critical" if spec.params.get("strict_release") else "warning",
            )
        )
        pkg = youtube_skills.check_packaging(title)
        raw_issues = pkg.get("issues", [])
        issues = [
            item
            for item in raw_issues
            if not (isinstance(item, (tuple, list)) and item and item[0] == "mobile")
        ]
        checks.append(
            _check(
                "title_lint",
                not issues,
                "title lint clean" if not issues else f"{len(issues)} packaging issue(s)",
                severity="critical" if spec.params.get("strict_release") else "warning",
                metrics={"issues": issues},
            )
        )
    return checks


@verifier("render")
def verify_render(spec: TaskSpec, result: WorkerResult, ctx: RunContext) -> list[CheckResult]:
    from tools import pipeline, visual_engine

    mp4 = _resolve(ctx, result.artifacts.get("output_mp4")) or _mp4_from_ctx(ctx)
    if not mp4 or not mp4.exists():
        return [_check("mp4_file", False, "rendered MP4 missing")]
    project_path = _project_json(ctx, result)
    fmt_type = "short"
    if project_path and project_path.exists():
        try:
            fmt_type = json.loads(project_path.read_text(encoding="utf-8")).get("format", "short")
        except (json.JSONDecodeError, OSError) as exc:
            return [_check("project_file", False, f"corrupt project.json: {exc}")]
    meta = pipeline.verify_rendered_mp4(mp4, format_type=fmt_type)
    checks = [
        _check("mp4_streams", bool(meta.get("valid")), meta.get("error", "valid synchronized streams and decoded video tail"), metrics=meta)
    ]
    target = (1080, 1920) if fmt_type == "short" else (1920, 1080)
    checks.append(
        _check(
            "mp4_dimensions",
            (meta.get("width"), meta.get("height")) == target,
            f"{meta.get('width')}x{meta.get('height')} expected {target[0]}x{target[1]}",
        )
    )
    checks.append(
        _check(
            "mp4_audio",
            meta.get("acodec") == "aac" and meta.get("sample_rate") == "48000",
            f"{meta.get('acodec')} @ {meta.get('sample_rate')} Hz",
        )
    )
    checks.append(_check("mp4_fps", meta.get("fps") == "30/1", f"{meta.get('fps')} fps"))
    checks.append(
        _check(
            "mp4_duration",
            float(meta.get("duration_s", 0)) >= 5.0,
            f"{meta.get('duration_s')} s",
        )
    )
    if project_path and project_path.exists():
        try:
            project = json.loads(project_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            project = {}
        for idx, scene in enumerate(project.get("scenes", [])):
            video = scene.get("video")
            if not video:
                continue
            clip = Path(video)
            if not clip.is_absolute():
                clip = project_path.parent / clip
            if not clip.exists():
                checks.append(_check(f"scene_{idx + 1}_clip", False, f"missing clip: {video}"))
                continue
            quality = visual_engine.verify_motion_quality(clip)
            checks.append(
                _check(
                    f"scene_{idx + 1}_motion",
                    bool(quality.get("valid", True)),
                    f"{quality.get('score')} flow={quality.get('mean_flow_px')}px",
                    severity="critical" if spec.params.get("strict_release") else "warning",
                    metrics=quality,
                )
            )
    return checks


@verifier("precompose")
def verify_precompose(spec: TaskSpec, result: WorkerResult, ctx: RunContext) -> list[CheckResult]:
    from tools import pipeline

    project_path = _project_json(ctx, result)
    if not project_path or not project_path.exists():
        return [_check("precompose", False, "project.json missing")]
    issues = pipeline.pre_compose_validate(project_path)
    missing = [issue for issue in issues if "missing asset" in issue.lower()]
    other = [issue for issue in issues if issue not in missing]
    checks = [
        _check(
            "precompose_assets",
            not missing,
            "all scene assets exist" if not missing else "; ".join(missing),
            metrics={"issues": missing},
        )
    ]
    if other:
        checks.append(
            _check(
                "precompose_quality",
                False,
                "; ".join(other),
                severity="critical" if spec.params.get("strict_release") else "warning",
                metrics={"issues": other},
            )
        )
    else:
        checks.append(_check("precompose_quality", True, "no pre-compose quality warnings"))
    return checks


@verifier("publish")
def verify_publish(spec: TaskSpec, result: WorkerResult, ctx: RunContext) -> list[CheckResult]:
    video_id = str(result.data.get("video_id", "")).strip()
    checks = [
        _check(
            "publish_video_id", bool(re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id)), f"video id {video_id or 'missing'}"
        )
    ]
    receipt_path = _resolve(ctx, result.artifacts.get("receipt"))
    verified_receipt = False
    receipt_err = None
    if receipt_path and receipt_path.exists():
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            verified_receipt = receipt.get("state") == "verified" and receipt.get("remote_id") == video_id
        except (json.JSONDecodeError, OSError) as exc:
            receipt_err = str(exc)
    checks.append(
        _check(
            "publish_receipt",
            verified_receipt,
            "verified durable receipt matches the remote ID"
            if verified_receipt
            else (f"corrupt upload receipt: {receipt_err}" if receipt_err else "missing or unverified upload receipt"),
        )
    )
    tracker = ctx.project_root / "CONTENT_TRACKER.md"
    if tracker.exists() and video_id:
        text = tracker.read_text(encoding="utf-8", errors="replace")
        checks.append(
            _check(
                "publish_tracker",
                video_id in text,
                "tracker contains the new video id"
                if video_id in text
                else "tracker was not updated; remote upload receipt is retained",
                severity="warning" if verified_receipt else "critical",
            )
        )
    return checks


@verifier("consistency")
def verify_consistency(spec: TaskSpec, result: WorkerResult, ctx: RunContext) -> list[CheckResult]:
    """Every name the repo references must resolve, or the change that removed it was incomplete.

    This is the gate that the thumbnail removal would have failed: six source files, three tests and
    six documents kept pointing at a module that no longer existed, and nothing noticed until a run
    tried to execute one of them.
    """
    from tools.orchestrator import impact

    index = impact.Index(ctx.root)
    findings = impact.find_stale(index)
    critical, warnings = impact.split_findings(findings)
    checks = [
        _check(
            "dangling_references",
            not critical,
            "no dangling imports, scripts or registry entries"
            if not critical
            else "; ".join(f.detail for f in critical[:6]),
            metrics={"critical": len(critical), "warning": len(warnings)},
        ),
        _check(
            "documentation_drift",
            not warnings,
            "documents and line citations match the code"
            if not warnings
            else "; ".join(f.detail for f in warnings[:6]),
            severity="critical" if spec.params.get("strict_release") else "warning",
            metrics={"warning": len(warnings)},
        ),
    ]
    return checks
