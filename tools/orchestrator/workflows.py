"""Workflow definitions: the master's playbooks."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .contracts import TaskSpec

STRICT_RELEASE_VERIFIERS = (
    "research", "script", "project", "render", "packaging", "precompose", "consistency",
)


@dataclass
class Workflow:
    name: str
    goal: str
    tasks: list[TaskSpec]
    params: dict = field(default_factory=dict)


def produce(
    *,
    topic: str,
    video_id: str,
    slug: str,
    genre: str = "3d_cgi",
    variant: str | None = None,
    channel: str = "cognitive_core",
    hook_min: int = 70,
    build: bool = True,
    publish: bool = False,
    public: bool = False,
    force_motion: bool = False,
    dossier: str | None = None,
    direct: bool = False,
) -> Workflow:
    if publish:
        raise ValueError(
            "produce cannot publish directly; finish production, then use release-existing with reviewed evidence"
        )
    effective_genre = variant or genre
    tasks = [
        TaskSpec(
            id="research",
            kind="research",
            title="Resolve verified primary-source dossier",
            params={"topic": topic, **({"dossier": dossier} if dossier else {})},
            verifiers=["research"],
            max_attempts=1,
        ),
        TaskSpec(
            id="script",
            kind="script",
            title="Write script and repair hook from dossier facts",
            params={"genre": effective_genre, "variant": effective_genre, "hook_min": hook_min},
            depends_on=["research"],
            verifiers=["script"],
            max_attempts=1,
        ),
    ]

    if direct:
        tasks.append(
            TaskSpec(
                id="director",
                kind="director",
                title="Showrunner visual blocking, directional lighting & sound design",
                params={
                    "topic": topic,
                    "video_id": video_id,
                    "slug": slug,
                    "genre": effective_genre,
                    "variant": effective_genre,
                    "channel": channel,
                },
                depends_on=["script"],
                verifiers=["direction"],
                max_attempts=1,
            )
        )

    tasks.append(
        TaskSpec(
            id="project",
            kind="project",
            title="Assemble project.json and upload kit",
            params={
                "topic": topic,
                "video_id": video_id,
                "slug": slug,
                "genre": effective_genre,
                "variant": effective_genre,
                "channel": channel,
            },
            depends_on=["director"] if direct else ["script"],
            verifiers=["project"],
            max_attempts=1,
        )
    )
    if build:
        tasks.extend(
            [
                TaskSpec(
                    id="build",
                    kind="build",
                    title="Render images, 3D clips and mastered MP4",
                    params={"force_motion": force_motion},
                    depends_on=["project"],
                    verifiers=["render"],
                    max_attempts=2,
                    timeout_s=3600,
                ),
                TaskSpec(
                    id="release",
                    kind="release",
                    title="Release gate: render + packaging + repo consistency",
                    depends_on=["build"],
                    verifiers=["render", "packaging", "precompose", "consistency"],
                    max_attempts=1,
                ),
            ]
        )
    params = {
        "topic": topic,
        "video_id": video_id,
        "slug": slug,
        "genre": effective_genre,
        "variant": effective_genre,
        "channel": channel,
        "build": build,
        "publish": publish,
        "public": public,
        "hook_min": hook_min,
    }
    goal = f"Produce {video_id} '{topic}'"
    return Workflow(name="produce", goal=goal, tasks=tasks, params=params)


def release_existing(
    *,
    project_json: str,
    evidence: str,
    publish: bool = False,
    privacy: str = "unlisted",
) -> Workflow:
    """Validate reviewed artifacts without invoking production workers."""
    if privacy not in {"unlisted", "public"}:
        raise ValueError("privacy must be unlisted or public")
    project = json.loads(Path(project_json).read_text(encoding="utf-8"))
    video_id = str(project.get("id", "")).strip()
    if not video_id:
        raise ValueError("project requires a video ID")
    params = {
        "project_json": str(project_json),
        "evidence": str(evidence),
        "video_id": video_id,
        "strict_evidence": True,
        "strict_release": True,
    }
    tasks = [
        TaskSpec(
            id="release",
            kind="release",
            title="Validate reviewed existing artifacts",
            params=params,
            verifiers=list(STRICT_RELEASE_VERIFIERS),
            max_attempts=1,
        )
    ]
    if publish:
        tasks.append(
            TaskSpec(
                id="publish",
                kind="publish",
                title="Upload reviewed artifacts via YouTube Data API",
                params={"public": privacy == "public"},
                depends_on=["release"],
                verifiers=["publish"],
                max_attempts=1,
                requires_approval=True,
            )
        )
    return Workflow(
        name="release-existing",
        goal=f"Release existing {video_id}",
        tasks=tasks,
        params={**params, "publish": publish, "privacy": privacy},
    )


def audit(*, search: str | None = None, glob: str | None = None) -> Workflow:
    tasks = [
        TaskSpec(
            id="audit",
            kind="audit",
            title="Scan all projects, renders, dossiers, tracker and cross-file references",
            max_attempts=1,
        )
    ]
    if search:
        tasks.append(
            TaskSpec(
                id="search",
                kind="search",
                title=f"Search code for '{search}'",
                params={"query": search, "glob": glob},
                depends_on=["audit"],
                max_attempts=1,
            )
        )
    return Workflow(
        name="audit",
        goal="Audit the repository and production artifacts",
        tasks=tasks,
        params={"search": search or "", "glob": glob or ""},
    )


def search(*, query: str, glob: str | None = None, max_results: int = 40) -> Workflow:
    return Workflow(
        name="search",
        goal=f"Search code for '{query}'",
        tasks=[
            TaskSpec(
                id="search",
                kind="search",
                title=f"Search code for '{query}'",
                params={"query": query, "glob": glob, "max_results": max_results},
                max_attempts=1,
            )
        ],
        params={"query": query, "glob": glob or ""},
    )


def custom(path: Path) -> Workflow:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    tasks = [TaskSpec.from_dict(item) for item in data.get("tasks", [])]
    if not tasks:
        raise ValueError("custom workflow has no tasks")
    return Workflow(
        name=str(data.get("name", "custom")),
        goal=str(data.get("goal", "Custom workflow")),
        tasks=tasks,
        params=data.get("params", {}),
    )
