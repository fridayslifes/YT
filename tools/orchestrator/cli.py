"""CLI for the master orchestrator.

Examples:
    python tools/master.py produce --topic "Ego Depletion" --id SH-17 --slug short_17_ego_depletion
    python tools/master.py audit
    python tools/master.py search "def build_and_verify"
    python tools/master.py impact --name thumbnail_studio
    python tools/master.py impact --all
    python tools/master.py status
    python tools/master.py resume 20261031-120000-produce --yes
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _ensure_runtime() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from tools.runtime import ensure_venv_cli

    ensure_venv_cli(Path(sys.argv[0]), sys.argv[1:])


def _print_state(state, *, verbose: bool = False) -> None:
    print("")
    print(f"Run:    {state.run_id}")
    print(f"Goal:   {state.goal}")
    print(f"Status: {state.status.upper()}")
    print(f"Report: {state.report_path or '(none)'}")
    print("")
    print(f"{'TASK':<12} {'KIND':<10} {'STATUS':<9} {'ATT':<4} SUMMARY")
    for record in state.tasks.values():
        summary = record.summary.replace("\n", " ")[:90]
        print(f"{record.spec.id:<12} {record.spec.kind:<10} {record.status.value:<9} {record.attempts:<4} {summary}")
    failures = [
        (record.spec.id, check.name, check.message)
        for record in state.tasks.values()
        for check in record.checks
        if not check.passed and check.severity == "critical"
    ]
    if failures:
        print("")
        print("Blocking checks:")
        for task, name, message in failures[:12]:
            print(f"  - {task}/{name}: {message[:180]}")
    if verbose:
        print("")
        print(json.dumps(state.to_dict(), indent=2, default=str))


def cmd_produce(args) -> int:
    if args.publish:
        print("Produce cannot publish directly. Finish production, then run release-existing with reviewed evidence.", file=sys.stderr)
        return 2
    state = run_production_workflow(
        topic=args.topic,
        video_id=args.id,
        slug=args.slug,
        genre=args.genre,
        variant=getattr(args, "variant", None),
        channel=args.channel,
        hook_min=args.hook_min,
        build=not args.blueprint,
        force_motion=args.force_motion,
        dossier=args.dossier,
        direct=getattr(args, "direct", False),
        dry_run=args.dry_run,
        approve=args.yes,
    )
    _print_state(state, verbose=args.json)
    return 0 if state.status in {"passed", "planned"} else 1


def run_production_workflow(
    *,
    topic: str,
    video_id: str,
    slug: str,
    genre: str = "3d_cgi",
    variant: str | None = None,
    channel: str = "cognitive_core",
    hook_min: int = 70,
    build: bool = True,
    force_motion: bool = False,
    dossier: str | None = None,
    direct: bool = False,
    dry_run: bool = False,
    approve: bool = False,
):
    """Internal canonical runner shared by the current and compatibility CLIs."""
    from tools.orchestrator.master import MasterAgent
    from tools.orchestrator.workflows import produce

    produce_kwargs = dict(
        topic=topic,
        video_id=video_id,
        slug=slug,
        genre=variant or genre,
        hook_min=hook_min,
        build=build,
        publish=False,
        force_motion=force_motion,
        dossier=dossier,
        direct=direct,
    )
    if variant is not None:
        produce_kwargs["variant"] = variant
    produce_kwargs["channel"] = channel
    workflow = produce(**produce_kwargs)
    return MasterAgent(ROOT).new_run(workflow, dry_run=dry_run, approve=approve)


def run_release_existing(
    project: Path, evidence: Path, *, publish: bool, public: bool = False, approve: bool = False
):
    """Run the one strict release path used by master and compatibility commands."""
    from tools.orchestrator.master import MasterAgent
    from tools.orchestrator.workflows import release_existing

    workflow = release_existing(
        project_json=str(project if project.is_absolute() else ROOT / project),
        evidence=str(evidence if evidence.is_absolute() else ROOT / evidence),
        publish=publish,
        privacy="public" if public else "unlisted",
    )
    return MasterAgent(ROOT).new_run(workflow, approve=approve)


def cmd_release_existing(args) -> int:
    if args.publish and not args.yes:
        print("Refusing to publish without --yes (irreversible external action).", file=sys.stderr)
        return 2
    state = run_release_existing(
        Path(args.project), Path(args.evidence), publish=args.publish,
        public=args.privacy == "public", approve=args.yes,
    )
    _print_state(state, verbose=args.json)
    return 0 if state.status == "passed" else 1


def cmd_prepare_release(args) -> int:
    """Create a deliberately unreviewed evidence bundle for human review."""
    from tools.schemas import prepare_release_draft

    project = Path(args.project)
    output = Path(args.output) if args.output else project.parent / "release_evidence.draft.json"
    try:
        draft = prepare_release_draft(project, output)
    except (OSError, ValueError, TypeError) as exc:
        print(f"Release draft could not be prepared: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote draft evidence: {draft}")
    print("Status: draft (unreviewed; strict release will reject it until human review is complete)")
    return 0


def legacy_upload_command(project: Path, evidence: Path | None, *, public: bool, approve: bool) -> int:
    """Keep older upload flags, but execute the strict reviewed release workflow."""
    if evidence is None or not approve:
        print(
            "Upload requires --evidence PATH and --yes. The strict release checks run before YouTube upload.",
            file=sys.stderr,
        )
        return 2
    project_json = project / "project.json" if project.is_dir() else project
    try:
        state = run_release_existing(project_json, evidence, publish=True, public=public, approve=True)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Release validation could not start: {exc}", file=sys.stderr)
        return 1
    _print_state(state)
    return 0 if state.status == "passed" else 1


def cmd_audit(args) -> int:
    from tools.orchestrator.master import MasterAgent
    from tools.orchestrator.workflows import audit

    workflow = audit(search=args.search, glob=args.glob)
    master = MasterAgent(ROOT)
    state = master.new_run(workflow, dry_run=args.dry_run, approve=False)
    _print_state(state, verbose=args.json)
    audit_record = state.tasks.get("audit")
    if audit_record and audit_record.data.get("findings"):
        print("")
        print("Audit findings:")
        for finding in audit_record.data["findings"][:20]:
            print(
                f"  - [{finding.get('level')}] {finding.get('project')} / "
                f"{finding.get('kind')}: {finding.get('detail')}"
            )
        for note in audit_record.data.get("tracker_findings", [])[:5]:
            print(f"  - tracker: {note}")
    search_record = state.tasks.get("search")
    if search_record and search_record.data.get("matches"):
        print("")
        for match in search_record.data["matches"][:20]:
            print(f"  {match['path']}:{match['line']}: {match['text'][:140]}")
    return 0 if state.status in {"passed", "planned"} else 1


def cmd_search(args) -> int:
    from tools.orchestrator.master import MasterAgent
    from tools.orchestrator.workflows import search

    workflow = search(query=args.query, glob=args.glob, max_results=args.max_results)
    state = MasterAgent(ROOT).new_run(workflow, dry_run=False, approve=False)
    _print_state(state, verbose=args.json)
    record = state.tasks.get("search")
    for match in (record.data.get("matches", []) if record else [])[: args.max_results]:
        print(f"{match['path']}:{match['line']}: {match['text']}")
    return 0


def cmd_impact(args) -> int:
    """Answer "what still points at this?" before and after a change."""
    from tools.orchestrator import impact

    index = impact.Index(ROOT)
    if args.all or not (args.name or args.path):
        findings = impact.find_stale(index)
        if args.json:
            print(json.dumps({"stats": impact.summary(index), "findings": [f.as_dict() for f in findings]}, indent=2))
        else:
            print(json.dumps(impact.summary(index), indent=2))
            for finding in findings:
                print(finding)
            print(f"\n{len(findings)} dangling reference(s).")
        return 1 if findings else 0

    sites = impact.impact(index, name=args.name, path=args.path)
    if args.json:
        print(json.dumps([s.as_dict() for s in sites], indent=2))
    else:
        for site in sites:
            print(site)
        print(f"\n{len(sites)} site(s) refer to {args.name or args.path}.")
    return 0 if sites else 1


def cmd_custom(args) -> int:
    from tools.orchestrator.master import MasterAgent
    from tools.orchestrator.workflows import custom

    workflow = custom(Path(args.spec))
    state = MasterAgent(ROOT).new_run(workflow, dry_run=args.dry_run, approve=args.yes)
    _print_state(state, verbose=args.json)
    return 0 if state.status in {"passed", "planned"} else 1


def cmd_status(args) -> int:
    from tools.orchestrator.state import RunStore

    store = RunStore(ROOT)
    state = store.load(args.run_id) if args.run_id else store.latest()
    if state is None:
        print("No runs yet.")
        return 0
    _print_state(state, verbose=args.json)
    return 0


def cmd_resume(args) -> int:
    from tools.atomic_files import LockBusy
    from tools.orchestrator.master import MasterAgent

    master = MasterAgent(ROOT)
    try:
        state = master.resume(args.run_id, approve=args.yes)
    except LockBusy:
        print(f"Run {args.run_id} is busy; another process is executing it. Try again after it finishes.", file=sys.stderr)
        return 1
    _print_state(state, verbose=args.json)
    return 0 if state.status in {"passed", "planned"} else 1


def cmd_workers(_args) -> int:
    from tools.orchestrator.verifiers import VERIFIERS
    from tools.orchestrator.workers import default_workers

    print("Workers:")
    for kind, worker in default_workers().items():
        print(f"  {kind:<10} {worker.description}")
    print("")
    print("Verifiers:")
    for name in VERIFIERS:
        print(f"  {name}")
    return 0


def cmd_genres(_args) -> int:
    from tools.genre_director import print_genre_menu

    print_genre_menu()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Master orchestrator: plan, delegate, verify, report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    produce = sub.add_parser("produce", help="Plan and run a full short-video production")
    produce.add_argument("--topic", required=True)
    produce.add_argument("--id", required=True, dest="id")
    produce.add_argument("--slug", required=True)
    produce.add_argument("--genre", default="3d_cgi")
    produce.add_argument("--variant", default=None, help="Canonical style variant (overrides --genre)")
    produce.add_argument("--channel", required=True, help="Target channel profile identifier")
    produce.add_argument("--hook-min", type=int, default=70)
    produce.add_argument("--dossier", help="Path to a verified dossier JSON")
    produce.add_argument("--blueprint", action="store_true", help="Research/script/project only; no render")
    produce.add_argument("--direct", action="store_true", default=False, help="Include showrunner director agent stage")
    produce.add_argument("--publish", action="store_true", help="Deprecated; publish through release-existing")
    produce.add_argument("--public", action="store_true", help="Public instead of unlisted")
    produce.add_argument("--yes", action="store_true", help="Approve irreversible actions (publish)")
    produce.add_argument("--force-motion", action="store_true", help="Re-render all scene clips")
    produce.add_argument("--dry-run", action="store_true", help="Write the plan only")
    produce.add_argument("--json", action="store_true")
    produce.set_defaults(func=cmd_produce)

    release = sub.add_parser("release-existing", help="Validate reviewed project, evidence and existing render")
    release.add_argument("--project", required=True)
    release.add_argument("--evidence", required=True)
    release.add_argument("--privacy", choices=["unlisted", "public"], default="unlisted")
    release.add_argument("--publish", action="store_true")
    release.add_argument("--yes", action="store_true", help="Approve upload after strict release gates")
    release.add_argument("--json", action="store_true")
    release.set_defaults(func=cmd_release_existing)

    prepare = sub.add_parser("prepare-release", help="Create an unreviewed evidence draft from a project")
    prepare.add_argument("--project", required=True)
    prepare.add_argument("--output", help="New evidence-draft path (defaults beside project.json)")
    prepare.set_defaults(func=cmd_prepare_release)

    audit = sub.add_parser("audit", help="Scan projects, renders, dossiers, tracker and cross-file references")
    audit.add_argument("--search", help="Optional code search to include")
    audit.add_argument("--glob", help="Optional search glob")
    audit.add_argument("--dry-run", action="store_true")
    audit.add_argument("--json", action="store_true")
    audit.set_defaults(func=cmd_audit)

    search = sub.add_parser("search", help="Search repository code")
    search.add_argument("query")
    search.add_argument("--glob")
    search.add_argument("--max-results", type=int, default=40)
    search.add_argument("--json", action="store_true")
    search.set_defaults(func=cmd_search)

    custom = sub.add_parser("run", help="Run a custom workflow JSON")
    custom.add_argument("--spec", required=True)
    custom.add_argument("--dry-run", action="store_true")
    custom.add_argument("--yes", action="store_true")
    custom.add_argument("--json", action="store_true")
    custom.set_defaults(func=cmd_custom)

    impact_p = sub.add_parser(
        "impact",
        help="Trace what a change touches: imports, flags, assets, docs and citations that still name it",
    )
    impact_p.add_argument("--name", help="Module, symbol, script, flag or asset name to trace")
    impact_p.add_argument("--path", help="Repository path to trace (same as --name, by file)")
    impact_p.add_argument("--all", action="store_true", help="List every dangling reference instead")
    impact_p.add_argument("--json", action="store_true")
    impact_p.set_defaults(func=cmd_impact)

    status = sub.add_parser("status", help="Show a run ledger")
    status.add_argument("run_id", nargs="?")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    resume = sub.add_parser("resume", help="Resume a run")
    resume.add_argument("run_id")
    resume.add_argument("--yes", action="store_true")
    resume.add_argument("--json", action="store_true")
    resume.set_defaults(func=cmd_resume)

    workers = sub.add_parser("workers", help="List workers and verifiers")
    workers.set_defaults(func=cmd_workers)

    genres = sub.add_parser("genres", help="Display visual genres and storybook production catalog")
    genres.set_defaults(func=cmd_genres)
    return parser


def main(argv: list[str] | None = None) -> int:
    _ensure_runtime()
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
