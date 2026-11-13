"""Specialist workers. Each returns evidence; the master decides if the task passed."""

from __future__ import annotations

import hashlib
import json
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path

from .contracts import Status, TaskSpec, WorkerResult
from .state import RunContext

TOOLS_DIR = Path(__file__).resolve().parent.parent
YT_ROOT = TOOLS_DIR.parent


def _project_json_from_ctx(ctx: RunContext, spec: TaskSpec | None = None) -> Path | None:
    if spec:
        raw = spec.params.get("project_json")
        if raw:
            path = Path(raw)
            return path if path.is_absolute() else ctx.root / path
    return ctx.project_json()


def _release_fingerprints(artifacts: dict[str, str], ctx: RunContext, *, public: bool) -> dict:
    """Bind a strict release to exact local inputs and the normalized upload request."""
    from tools.upload_api import parse_upload_kit

    paths = {}
    fingerprints = {}
    for name in ("project_json", "evidence", "upload_kit", "output_mp4"):
        path = Path(artifacts[name])
        path = (path if path.is_absolute() else ctx.root / path).resolve()
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        paths[name] = path
        fingerprints[name] = {"path": str(path), "sha256": digest.hexdigest()}
    project_dir = paths["project_json"].parent
    kits = sorted(path.resolve() for path in project_dir.glob("UPLOAD_KIT*.md"))
    canonical = (project_dir / "output" / f"{project_dir.name}.mp4").resolve()
    if kits != [paths["upload_kit"]] or canonical != paths["output_mp4"]:
        raise ValueError("release artifact selection changed")
    project = json.loads(paths["project_json"].read_text(encoding="utf-8"))
    meta = parse_upload_kit(paths["upload_kit"])
    metadata = {
        "snippet": {
            "title": (meta.get("title") or "").strip(),
            "description": meta.get("description") or "",
            "tags": meta.get("tags") or [],
            "categoryId": "27",
        },
        "status": {
            "privacyStatus": "public" if public else "unlisted",
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": project.get("contains_synthetic_media") is True,
        },
    }
    metadata_hash = hashlib.sha256(
        json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return {"schema_version": 1, "artifacts": fingerprints, "metadata_sha256": metadata_hash}


class Worker(ABC):
    kind: str = "worker"
    description: str = ""

    @abstractmethod
    def run(self, spec: TaskSpec, ctx: RunContext) -> WorkerResult:
        raise NotImplementedError


class ResearchWorker(Worker):
    kind = "research"
    description = "Resolve a verified primary-source dossier for factual videos; fiction is exempt."

    def run(self, spec: TaskSpec, ctx: RunContext) -> WorkerResult:
        from tools import creative_engine, fact_check

        topic = str(spec.params.get("topic", "")).strip()
        if not topic:
            return WorkerResult(ok=False, summary="missing topic", error="topic is required", retryable=False)

        content_type = fact_check.normalize_content_type(spec.params.get("content_type", "factual"))
        if content_type == "fiction":
            return WorkerResult(
                ok=True,
                summary="fiction: research/fact-check exempt",
                facts=["Fiction asserts no factual claims; no dossier or web verification required."],
                metrics={"content_type": "fiction"},
                data={"content_type": "fiction", "dossier": {}, "fact_check": fact_check.exempt_report("fiction")},
            )

        custom = spec.params.get("dossier")
        if custom:
            path = Path(custom)
            if not path.is_absolute():
                path = ctx.root / path
            if not path.exists():
                return WorkerResult(ok=False, summary="dossier not found", error=str(path), retryable=False)
            try:
                dossier = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                return WorkerResult(ok=False, summary="invalid dossier", error=str(exc), retryable=False)
            if not isinstance(dossier, dict):
                return WorkerResult(
                    ok=False, summary="invalid dossier", error="dossier must be a JSON object", retryable=False
                )
            dossier.setdefault("_verified", False)
            dossier["_source"] = str(path)
            dossier.setdefault("_synthetic", False)
        else:
            try:
                match_key, value = creative_engine.find_dossier_entry(topic)
            except creative_engine.AmbiguousDossier:
                return WorkerResult(
                    ok=False, summary=f"ambiguous dossier for '{topic}'",
                    error="Multiple dossiers match; pass --dossier with the reviewed source.", retryable=False,
                )
            except creative_engine.MissingDossier:
                return WorkerResult(
                    ok=False,
                    summary=f"no verified dossier for '{topic}'",
                    error=(
                        "Research stops here: add a real entry to "
                        "channel_assets/scientific_dossiers.json (researchers, year, publication, "
                        "experiment, statistic) or pass --dossier path.json. "
                        "The synthetic fallback is intentionally disabled for the master."
                    ),
                    facts=[f"No verified dossier exists for {topic}."],
                    retryable=False,
                )
            dossier = dict(value)
            # The checked-in source is trusted when older entries omit markers. Explicit
            # false, synthetic, or malformed markers remain for the independent gate.
            dossier.setdefault("_verified", True)
            dossier["_source"] = f"channel_assets/scientific_dossiers.json#{match_key}"
            dossier.setdefault("_synthetic", False)

        summary = (
            f"{dossier.get('primary_researchers')} ({dossier.get('year')}, "
            f"{dossier.get('publication')}) | {dossier.get('quantitative_stat')}"
        )
        return WorkerResult(
            ok=True,
            summary=summary,
            facts=[
                f"Source: {dossier.get('_source')}",
                f"Study: {dossier.get('primary_researchers')} ({dossier.get('year')}) - {dossier.get('publication')}",
                f"Stat: {dossier.get('quantitative_stat')}",
            ],
            metrics={
                "topic": dossier.get("topic", topic),
                "researchers": dossier.get("primary_researchers"),
                "year": dossier.get("year"),
                "stat": dossier.get("quantitative_stat"),
            },
            data={"dossier": dossier, "content_type": "factual"},
        )


class ScriptWorker(Worker):
    kind = "script"
    description = "Write the 8-beat script and repair weak hooks using dossier facts only."

    def run(self, spec: TaskSpec, ctx: RunContext) -> WorkerResult:
        from tools import creative_engine, youtube_skills

        dossier = ctx.dep_data("research").get("dossier") or {}
        genre = str(spec.params.get("genre") or spec.params.get("variant") or "3d_cgi")
        min_hook = int(spec.params.get("hook_min", 70))
        scenes = creative_engine.choreograph_scenes(dossier, genre=genre)
        if not scenes:
            return WorkerResult(ok=False, summary="no scenes", error="choreographer returned no scenes", retryable=False)

        original = scenes[0].get("text", "")
        score = int(youtube_skills.score_hook(original).get("verdict", 0))
        healed = False
        if score < min_hook:
            year = str(dossier.get("year", ""))
            stat = str(dossier.get("quantitative_stat", ""))
            researchers = str(dossier.get("primary_researchers", ""))
            topic = str(dossier.get("topic", "this effect"))
            mechanism = str(dossier.get("biological_mechanism", "")).split(".")[0]
            candidates = [
                str(dossier.get("best_hook", "")),
                f"{dossier.get('broken_assumption', '')}",
                f"Your brain treats {topic.lower()} as a threat: {mechanism}.",
            ]
            if year and stat:
                candidates.append(
                    f"In {year}, {researchers} measured {stat} in {topic.lower()}."
                )
            best_text, best_score = original, score
            for candidate in candidates:
                candidate = candidate.strip()
                if not candidate:
                    continue
                candidate_score = int(youtube_skills.score_hook(candidate).get("verdict", 0))
                if candidate_score > best_score:
                    best_text, best_score = candidate, candidate_score
            if best_text != original:
                scenes[0]["text"] = best_text
                healed = True
                score = best_score

        claims = []
        for field in (
            "year",
            "primary_researchers",
            "publication",
            "quantitative_stat",
            "comparison_text",
            "broken_assumption",
            "biological_mechanism",
        ):
            value = dossier.get(field)
            if value:
                claims.append({"field": field, "value": str(value)})
        if healed:
            claims.append({"field": "best_hook", "value": scenes[0]["text"]})

        words = len(re.findall(r"\b\w+\b", " ".join(str(sc.get("text", "")) for sc in scenes)))
        summary = (
            f"{len(scenes)} scenes | {words} words | hook {score}/100 "
            f"({'repaired' if healed else 'original'})"
        )
        return WorkerResult(
            ok=True,
            summary=summary,
            facts=[f"Hook: {scenes[0].get('text', '')[:140]}"],
            metrics={
                "scenes": len(scenes),
                "words": words,
                "hook_score": score,
                "hook_repaired": healed,
                "genre": genre,
            },
            data={"scenes": scenes, "dossier": dossier, "claims": claims},
        )


class DirectorWorker(Worker):
    kind = "director"
    description = "Choreograph spatial blocking, movement vectors, directional lighting, and sound."

    def run(self, spec: TaskSpec, ctx: RunContext) -> WorkerResult:
        from tools.director_agent import ShowrunnerDirector

        script_record = ctx.dep_data("script") or {}
        scenes = script_record.get("scenes", [])
        if not scenes:
            return WorkerResult(
                ok=False,
                summary="script scenes missing",
                error="DirectorWorker requires scenes from script task.",
                retryable=False,
            )

        dossier = (
            script_record.get("dossier")
            or (ctx.dep_data("research").get("dossier") if "research" in ctx.state.tasks else {})
            or {}
        )

        channel = str(spec.params.get("channel", "default"))
        genre = str(spec.params.get("genre") or spec.params.get("variant") or "3d_cgi")
        video_id = str(spec.params.get("video_id", "SH-01"))
        topic = str(spec.params.get("topic") or dossier.get("topic") or "")

        director = ShowrunnerDirector(channel=channel, genre=genre)
        manifest = director.direct_video(
            script_scenes=scenes,
            dossier=dossier,
            video_id=video_id,
            topic=topic,
        )

        slug = str(spec.params.get("slug") or f"short_{video_id.lower().replace('-', '_')}")
        target_dir = ctx.root / "shorts" / slug
        target_dir.mkdir(parents=True, exist_ok=True)

        manifest_path = target_dir / "director_manifest.json"
        manifest_path.write_text(manifest.to_json(indent=2), encoding="utf-8")

        pitch_path = target_dir / "DIRECTOR_PITCH.md"
        pitch_path.write_text(manifest.format_director_pitch(), encoding="utf-8")

        return WorkerResult(
            ok=True,
            summary=f"Directed {len(manifest.scenes)} scenes: spatial blocking, lighting angles & sound design",
            artifacts={
                "director_manifest": str(manifest_path),
                "director_pitch": str(pitch_path),
            },
            metrics={
                "scenes_directed": len(manifest.scenes),
                "genre": genre,
                "channel": channel,
            },
            facts=[
                f"Directorial Logline: {manifest.logline}",
                f"Pitch board: {pitch_path.relative_to(ctx.root)}",
            ],
            data=manifest.to_dict(),
        )


class ProjectWorker(Worker):
    kind = "project"
    description = "Assemble project.json and the upload kit from verified evidence."

    def run(self, spec: TaskSpec, ctx: RunContext) -> WorkerResult:
        from tools import creative_engine

        dossier = ctx.dep_data("script").get("dossier") or ctx.dep_data("research").get("dossier") or {}
        director_data = ctx.dep_data("director") or {}
        directed_scenes = director_data.get("scenes")
        if directed_scenes:
            scenes = [
                {
                    "id": f"s{sc['scene_index']:02d}",
                    "image": f"images/s{sc['scene_index']:02d}.jpg",
                    "video": f"videos/s{sc['scene_index']:02d}.mp4",
                    "text": sc["text"],
                    "prompt": sc["synthesized_prompt"],
                    "preset": sc["camera"]["trajectory_preset"],
                    "motion": sc["camera"]["trajectory_preset"],
                    "cap_y": sc["camera"]["safe_zone_anchor"],
                    **({"overlay": sc["overlay"]} if sc.get("overlay") else {}),
                    **({"stat_card": sc["stat_card"]} if sc.get("stat_card") else {}),
                }
                for sc in directed_scenes
            ]
        else:
            scenes = ctx.dep_data("script").get("scenes")

        topic = str(spec.params.get("topic", dossier.get("topic", "")))
        video_id = str(spec.params.get("video_id", ""))
        slug = str(spec.params.get("slug", ""))
        genre = str(spec.params.get("genre") or spec.params.get("variant") or "3d_cgi")
        variant = spec.params.get("variant")
        channel_id = str(spec.params.get("channel") or spec.params.get("channel_id") or "default")
        if not (topic and video_id and slug):
            return WorkerResult(
                ok=False,
                summary="missing project identity",
                error="topic/id/slug required",
                retryable=False,
            )

        try:
            proj_path = creative_engine.generate_creative_project(
                topic=topic,
                video_id=video_id,
                slug=slug,
                genre=genre,
                variant=variant,
                channel_id=channel_id,
                dossier=dossier,
                scenes=scenes,
                overwrite=bool(spec.params.get("overwrite", False)),
                content_type=str(spec.params.get("content_type", "factual")),
            )
        except FileExistsError as exc:
            return WorkerResult(ok=False, summary="project collision", error=str(exc), retryable=False)
        kits = sorted(proj_path.parent.glob("UPLOAD_KIT*.md"))
        return WorkerResult(
            ok=True,
            summary=str(proj_path.relative_to(ctx.root)),
            artifacts={
                "project_json": str(proj_path),
                "upload_kit": str(kits[0]) if kits else "",
                "project_dir": str(proj_path.parent),
            },
            facts=[f"Blueprint assembled at {proj_path.relative_to(ctx.root)}"],
            data={"project_json": str(proj_path)},
        )


class FactCheckWorker(Worker):
    kind = "factcheck"
    description = "Fact-check the script's factual claims via live web research; fiction is exempt."

    def run(self, spec: TaskSpec, ctx: RunContext) -> WorkerResult:
        from tools import fact_check

        project_json = _project_json_from_ctx(ctx, spec)
        if not project_json or not project_json.exists():
            return WorkerResult(ok=False, summary="project missing", error=str(project_json), retryable=False)
        try:
            project = json.loads(project_json.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return WorkerResult(ok=False, summary="invalid project", error=str(exc), retryable=False)

        content_type = fact_check.normalize_content_type(
            spec.params.get("content_type") or project.get("content_type", "factual")
        )
        report_path = project_json.parent / "fact_check.json"

        if content_type == "fiction":
            report = fact_check.exempt_report("fiction")
        else:
            dossier = ctx.dep_data("script").get("dossier") or ctx.dep_data("research").get("dossier") or {}
            if dossier and dossier.get("_verified") is True and dossier.get("_synthetic", False) is False:
                # A verified primary-source dossier already grounds the factual claims.
                report = fact_check.dossier_report()
            else:
                try:
                    report = fact_check.check_project({**project, "content_type": "factual"})
                except fact_check.FactCheckError as exc:
                    return WorkerResult(ok=False, summary="fact-check cannot run", error=str(exc), retryable=False)

        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        ok = bool(report.get("passed"))
        return WorkerResult(
            ok=ok,
            summary=f"fact-check {report['status']} ({report.get('checked', 0)} claim(s))",
            artifacts={"fact_check": str(report_path)},
            facts=[report.get("note", "")] + [f"unverified: {f}" for f in report.get("flags", [])[:5]],
            metrics={
                "content_type": content_type,
                "status": report["status"],
                "checked": report.get("checked", 0),
                "flags": len(report.get("flags", [])),
            },
            data={"fact_check": report, "content_type": content_type},
            error="" if ok else "factual claims unverified by live web research",
            retryable=False,
        )


class BuildWorker(Worker):
    kind = "build"
    description = "Render scene images, 3D spatial clips and the mastered MP4."

    def run(self, spec: TaskSpec, ctx: RunContext) -> WorkerResult:
        import sys
        from tools import pipeline, processes

        project_json = _project_json_from_ctx(ctx, spec)
        if not project_json or not project_json.exists():
            return WorkerResult(ok=False, summary="project missing", error=str(project_json), retryable=False)
        started = time.time()
        force_motion = bool(spec.params.get("force_motion", False))
        fn_mod = getattr(pipeline.build_and_verify, "__module__", "")
        if sys.platform == "darwin" and fn_mod == "tools.pipeline":
            # Execute in a clean exec'd Python interpreter so macOS libobjc/libdispatch/Metal/ONNXRuntime
            # never abort inside a fork-without-exec worker child.
            cmd = [
                sys.executable,
                "-c",
                (
                    "import json, pathlib, sys; "
                    "from tools import pipeline; "
                    "meta = pipeline.build_and_verify("
                    "pathlib.Path(sys.argv[1]), hw_accel=True, force_motion=(sys.argv[2] == '1')"
                    "); "
                    "print('__BUILD_META__:' + json.dumps(meta))"
                ),
                str(project_json),
                "1" if force_motion else "0",
            ]
            proc = processes.run_process(
                cmd,
                timeout_s=max(30, int(spec.timeout_s)),
                cwd=ctx.root,
                capture_output=True,
                text=True,
                check=False,
            )
            meta = {}
            for line in reversed((proc.stdout or "").splitlines()):
                if line.startswith("__BUILD_META__:"):
                    try:
                        meta = json.loads(line.split("__BUILD_META__:", 1)[1])
                    except Exception:
                        meta = {}
                    break
            if proc.returncode != 0 and not meta:
                err_tail = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()[-600:]
                return WorkerResult(
                    ok=False,
                    summary="build subprocess failed",
                    artifacts={"project_json": str(project_json)},
                    error=err_tail or f"exit code {proc.returncode}",
                    retryable=True,
                )
        else:
            meta = pipeline.build_and_verify(
                project_json,
                hw_accel=True,
                force_motion=force_motion,
            )
        output = project_json.parent / "output" / f"{project_json.parent.name}.mp4"
        ok = bool(meta.get("valid")) and output.exists()
        return WorkerResult(
            ok=ok,
            summary=(
                f"{meta.get('width')}x{meta.get('height')} @ {meta.get('fps')} | "
                f"{meta.get('duration_s')}s | {meta.get('bitrate_mbps')} Mbps"
            ),
            artifacts={"project_json": str(project_json), "output_mp4": str(output)},
            metrics={**meta, "render_s": round(time.time() - started, 1)},
            facts=[f"Master MP4: {output.relative_to(ctx.root)}"],
            data=meta,
            error="" if ok else "render did not produce a valid MP4",
            retryable=True,
        )


class ReleaseWorker(Worker):
    kind = "release"
    description = "Collect existing artifacts; independent verifiers enforce release gates."

    def run(self, spec: TaskSpec, ctx: RunContext) -> WorkerResult:
        if spec.params.get("project_json") or spec.params.get("evidence"):
            try:
                project_path = _project_json_from_ctx(ctx, spec)
                evidence_path = Path(spec.params["evidence"])
                if not evidence_path.is_absolute():
                    evidence_path = ctx.root / evidence_path
                project = json.loads(project_path.read_text(encoding="utf-8"))
                evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
                kits = sorted(project_path.parent.glob("UPLOAD_KIT*.md"))
                if len(kits) != 1:
                    raise ValueError("existing release requires exactly one upload kit")
                output = project_path.parent / "output" / f"{project_path.parent.name}.mp4"
                if not output.is_file():
                    raise ValueError(f"canonical render missing: {output}")
                artifacts = {
                    "project_json": str(project_path),
                    "upload_kit": str(kits[0]),
                    "output_mp4": str(output),
                    "evidence": str(evidence_path),
                }
                fingerprints = _release_fingerprints(
                    artifacts, ctx, public=ctx.state.params.get("privacy", "unlisted") == "public"
                )
                return WorkerResult(
                    ok=True,
                    summary="imported reviewed artifacts without regeneration",
                    artifacts=artifacts,
                    data={
                        "evidence": evidence,
                        "dossier": evidence.get("dossier", {}),
                        "claims": evidence.get("claims", []),
                        "editorial_suggestions": evidence.get("editorial_suggestions", []),
                        "scenes": project.get("scenes", []),
                        "release_fingerprints": fingerprints,
                    },
                    retryable=False,
                )
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
                return WorkerResult(
                    ok=False, summary="existing artifact import failed", error=str(exc), retryable=False
                )
        artifacts: dict[str, str] = {}
        for task_id in ("build",):
            record = ctx.state.tasks.get(task_id)
            if record:
                artifacts.update(record.artifacts)
        return WorkerResult(ok=True, summary="release gate collected the build artifacts", artifacts=artifacts)


class PublishWorker(Worker):
    kind = "publish"
    description = "Upload only after the release gate passes."

    def run(self, spec: TaskSpec, ctx: RunContext) -> WorkerResult:
        from tools.upload_api import resolve_expected_channel_id, upload_via_api
        from .workflows import STRICT_RELEASE_VERIFIERS

        if not ctx.approve:
            return WorkerResult(
                ok=False,
                summary="publish requires approval",
                error="re-run with --publish --yes",
                retryable=False,
            )
        project_json = _project_json_from_ctx(ctx, spec)
        project_dir = project_json.parent if project_json and project_json.exists() else None
        if not project_dir:
            return WorkerResult(ok=False, summary="project missing", error="no project directory", retryable=False)
        release = ctx.state.tasks.get("release")
        if (
            ctx.state.workflow != "release-existing"
            or not release
            or release.spec.kind != "release"
            or release.spec.params.get("strict_release") is not True
            or release.spec.params.get("strict_evidence") is not True
            or set(release.spec.verifiers) != set(STRICT_RELEASE_VERIFIERS)
            or len(release.spec.verifiers) != len(STRICT_RELEASE_VERIFIERS)
            or release.status != Status.PASSED
            or not release.data.get("release_fingerprints")
            or spec.depends_on != ["release"]
            or not spec.requires_approval
        ):
            return WorkerResult(
                ok=False, summary="strict release contract missing",
                error="A passed release-existing run with every strict verifier and input fingerprints is required.",
                retryable=False,
            )
        try:
            current = _release_fingerprints(
                {**release.artifacts, "project_json": str(project_json)}, ctx,
                public=bool(spec.params.get("public", False)),
            )
            if current != release.data["release_fingerprints"]:
                raise ValueError("project, evidence, upload kit, MP4 or upload metadata changed")
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            return WorkerResult(
                ok=False, summary="release inputs changed; upload blocked",
                error=f"Release inputs changed or cannot be verified: {exc}. Rerun release-existing validation before publish.",
                retryable=False,
            )
        project = json.loads(project_json.read_text(encoding="utf-8"))
        evidence_data = None
        if release and release.artifacts.get("evidence"):
            ev_path = Path(release.artifacts["evidence"])
            if not ev_path.is_absolute():
                ev_path = ctx.root / ev_path
            if ev_path.exists():
                try:
                    evidence_data = json.loads(ev_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError) as exc:
                    return WorkerResult(
                        ok=False,
                        summary="corrupt evidence artifact",
                        error=f"Cannot parse evidence file {ev_path}: {exc}",
                        retryable=False,
                    )

        channel = project.get("channel") or project.get("channel_id", "default")
        from tools.policy_gate import evaluate_policy_gate

        policy_report = evaluate_policy_gate(
            project,
            evidence=evidence_data,
            channel=channel,
        )
        if not policy_report.passed:
            return WorkerResult(
                ok=False,
                summary="policy gate failed; upload blocked",
                error="Upload blocked by policy gate:\n" + "\n".join(f"- {v}" for v in policy_report.violations),
                retryable=False,
            )
        receipt = ctx.root / "channel_assets" / "upload_receipts" / f"{project['id']}.json"
        expected_channel_id = resolve_expected_channel_id(
            channel=channel,
            explicit_id=spec.params.get("expected_channel_id"),
        )
        try:
            live_id = upload_via_api(
                project_dir,
                public=bool(spec.params.get("public", False)),
                expected_channel_id=expected_channel_id,
                contains_synthetic_media=project.get("contains_synthetic_media") is True,
                receipt_path=receipt,
            )
        except SystemExit as exc:
            return WorkerResult(
                ok=False,
                summary="upload aborted",
                error=f"uploader exited with code {exc.code}",
                retryable=False,
            )
        if not live_id:
            return WorkerResult(ok=False, summary="upload returned no video id", error="upload failed", retryable=False)
        return WorkerResult(
            ok=True,
            summary=f"uploaded {live_id}",
            artifacts={"url": f"https://youtu.be/{live_id}", "receipt": str(receipt)},
            facts=[f"Live: https://youtu.be/{live_id}"],
            data={"video_id": live_id},
            retryable=False,
        )


class SearchWorker(Worker):
    kind = "search"
    description = "Search the repository read-only."

    def run(self, spec: TaskSpec, ctx: RunContext) -> WorkerResult:
        query = str(spec.params.get("query", "")).strip()
        result = ctx.tools.search_code(
            query,
            glob=spec.params.get("glob"),
            context=int(spec.params.get("context", 1)),
            max_results=int(spec.params.get("max_results", 40)),
        )
        matches = result["matches"]
        facts = [f"{m['path']}:{m['line']} {m['text'][:120]}" for m in matches[:10]]
        return WorkerResult(
            ok=True,
            summary=f"{len(matches)} match(es) for '{query}'",
            facts=facts,
            metrics={"matches": len(matches), "engine": result["engine"]},
            data=result,
        )


class AuditWorker(Worker):
    kind = "audit"
    description = "Scan projects, renders, dossiers, tracker and cross-file consistency."

    def run(self, spec: TaskSpec, ctx: RunContext) -> WorkerResult:
        from tools import creative_engine, pipeline

        findings: list[dict] = []
        projects: list[Path] = []
        for pattern in ("shorts/*/project.json", "long_form/*/project.json"):
            projects.extend(sorted(ctx.root.glob(pattern)))
        valid_projects: list[tuple[Path, dict]] = []
        skipped = 0
        for project_path in projects:
            try:
                project = json.loads(project_path.read_text(encoding="utf-8"))
                if not isinstance(project, dict):
                    raise ValueError("project root must be an object")
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                skipped += 1
                findings.append({
                    "level": "warning", "project": project_path.parent.name, "kind": "project",
                    "detail": f"malformed project JSON: {exc}",
                })
                continue
            valid_projects.append((project_path, project))
            project_dir = project_path.parent
            is_long = project.get("format") == "long"
            mp4 = project_dir / "output" / f"{project_dir.name}.mp4"
            if not mp4.exists():
                mp4s = sorted((project_dir / "output").glob("*.mp4"))
                mp4 = mp4s[0] if mp4s else mp4
            if mp4.exists():
                meta = pipeline.verify_rendered_mp4(mp4, format_type="long" if is_long else "short")
                if not meta.get("valid"):
                    findings.append({"level": "critical", "project": project.get("id"), "kind": "mp4", "detail": meta.get("error", "invalid")})
            else:
                findings.append({"level": "info", "project": project.get("id"), "kind": "blueprint", "detail": "no rendered MP4"})
            issues = pipeline.pre_compose_validate(project_path)
            for issue in issues:
                findings.append(
                    {
                        "level": "warning",
                        "project": project.get("id"),
                        "kind": "precompose",
                        "detail": issue,
                    }
                )

        dossiers = creative_engine.load_dossiers()
        dossier_keys = set(dossiers.keys())
        for project_path, project in valid_projects:
            concept = creative_engine.normalize_topic_key(str(project.get("concept") or project.get("topic") or ""))
            covered = any(concept == key or concept in key or key in concept for key in dossier_keys)
            if concept and not covered:
                findings.append(
                    {
                        "level": "warning",
                        "project": project.get("id"),
                        "kind": "research",
                        "detail": f"no dossier for '{project.get('concept')}'",
                    }
                )

        from tools.orchestrator import impact

        stale_index = impact.Index(ctx.root)
        for finding in impact.find_stale(stale_index):
            findings.append(
                {
                    "level": impact.severity(finding),
                    "project": "REPO",
                    "kind": "consistency",
                    "detail": f"{finding.detail} ({finding.sites[0].file}:{finding.sites[0].line})",
                }
            )

        tracker_findings: list[str] = []
        tracker = ctx.root / "CONTENT_TRACKER.md"
        if tracker.exists():
            text = tracker.read_text(encoding="utf-8", errors="replace")
            sh_rows = len(re.findall(r"^\| \*\*SH-", text, re.M))
            summary_match = re.search(r"Shorts Uploaded & Live\*\* \| \*\*(\d+)\*\*", text)
            if summary_match:
                claimed = int(summary_match.group(1))
                if claimed != sh_rows:
                    tracker_findings.append(
                        f"tracker summary says {claimed} shorts live; table has {sh_rows} short rows"
                    )
            if "As of Oct 25" in text:
                tracker_findings.append("tracker header is dated Oct 25 but contains later uploads")

        media_assessed = sum(
            1 for project_path, project in valid_projects
            if (project_path.parent / "output" / f"{project_path.parent.name}.mp4").exists()
            or bool(list((project_path.parent / "output").glob("*.mp4")))
        )
        critical = [f for f in findings if f["level"] == "critical"]
        warnings = [f for f in findings if f["level"] == "warning"]
        media_summary = (
            f"{media_assessed} media assessed"
            if media_assessed else "0 media assessed (no retained media assessed)"
        )
        summary = (
            f"{len(projects)} projects scanned | {media_summary} | {skipped} skipped | "
            f"{len(critical)} critical | "
            f"{len(warnings)} warnings | {len(tracker_findings)} tracker notes"
        )
        facts = [f"{f['level'].upper()} {f['project']} {f['kind']}: {f['detail']}" for f in findings[:12]]
        facts.extend(f"TRACKER: {note}" for note in tracker_findings)
        return WorkerResult(
            ok=not critical,
            summary=summary,
            facts=facts,
            metrics={
                "scanned": len(projects),
                "projects": len(projects),
                "media_assessed": media_assessed,
                "skipped": skipped,
                "critical": len(critical),
                "warnings": len(warnings),
                "tracker_notes": len(tracker_findings),
            },
            data={
                "findings": findings,
                "tracker_findings": tracker_findings,
                "reports": [],
            },
            error=f"audit found {len(critical)} critical issue(s)" if critical else "",
            retryable=False,
        )


def default_workers() -> dict[str, Worker]:
    workers = [
        ResearchWorker(),
        ScriptWorker(),
        DirectorWorker(),
        ProjectWorker(),
        FactCheckWorker(),
        BuildWorker(),
        ReleaseWorker(),
        PublishWorker(),
        SearchWorker(),
        AuditWorker(),
    ]
    return {worker.kind: worker for worker in workers}
