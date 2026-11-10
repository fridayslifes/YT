#!/usr/bin/env python3
"""FrameForge Rich Terminal Output Engine (v1.0).

Provides beautiful, human-readable terminal output utilities for the entire
FrameForge pipeline — status badges, progress bars, formatted tables,
project cards, and agent report summaries.

Zero external dependencies beyond Python stdlib. Works in any terminal.
"""

from __future__ import annotations

import os
import shutil
import sys
import textwrap
from typing import List


# ─── Terminal capabilities ───────────────────────────────────────────────────

def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


USE_COLOR = _supports_color()
TERM_WIDTH = min(shutil.get_terminal_size((100, 24)).columns, 120)


# ─── ANSI color codes ────────────────────────────────────────────────────────

class C:
    """ANSI color shortcuts."""
    RESET = "\033[0m" if USE_COLOR else ""
    BOLD = "\033[1m" if USE_COLOR else ""
    DIM = "\033[2m" if USE_COLOR else ""
    ITALIC = "\033[3m" if USE_COLOR else ""
    UNDERLINE = "\033[4m" if USE_COLOR else ""

    # Foreground
    RED = "\033[91m" if USE_COLOR else ""
    GREEN = "\033[92m" if USE_COLOR else ""
    YELLOW = "\033[93m" if USE_COLOR else ""
    BLUE = "\033[94m" if USE_COLOR else ""
    MAGENTA = "\033[95m" if USE_COLOR else ""
    CYAN = "\033[96m" if USE_COLOR else ""
    WHITE = "\033[97m" if USE_COLOR else ""
    GRAY = "\033[90m" if USE_COLOR else ""

    # Background
    BG_GREEN = "\033[42m" if USE_COLOR else ""
    BG_YELLOW = "\033[43m" if USE_COLOR else ""
    BG_RED = "\033[41m" if USE_COLOR else ""
    BG_BLUE = "\033[44m" if USE_COLOR else ""
    BG_MAGENTA = "\033[45m" if USE_COLOR else ""
    BG_CYAN = "\033[46m" if USE_COLOR else ""


# ─── Status badges ───────────────────────────────────────────────────────────

STATUS_BADGES = {
    "PASS":      f"{C.BG_GREEN}{C.BOLD}{C.WHITE} ✅ PASS    {C.RESET}",
    "HEALED":    f"{C.BG_CYAN}{C.BOLD}{C.WHITE} 🔄 HEALED  {C.RESET}",
    "WARN":      f"{C.BG_YELLOW}{C.BOLD}{C.WHITE} ⚠️  WARN    {C.RESET}",
    "FAIL":      f"{C.BG_RED}{C.BOLD}{C.WHITE} ❌ FAIL    {C.RESET}",
    "SKIPPED":   f"{C.BG_MAGENTA}{C.BOLD}{C.WHITE} ⏭️  SKIP    {C.RESET}",
    "BLUEPRINT": f"{C.BG_BLUE}{C.BOLD}{C.WHITE} 🔵 READY   {C.RESET}",
    "DRAFT":     f"{C.BG_MAGENTA}{C.BOLD}{C.WHITE} 📝 DRAFT   {C.RESET}",
    "UPLOADED":  f"{C.BG_GREEN}{C.BOLD}{C.WHITE} 🚀 LIVE    {C.RESET}",
}

# Plain-text fallbacks
STATUS_BADGES_PLAIN = {
    "PASS":      "[  PASS  ]",
    "HEALED":    "[ HEALED ]",
    "WARN":      "[  WARN  ]",
    "FAIL":      "[  FAIL  ]",
    "SKIPPED":   "[ SKIPPED]",
    "BLUEPRINT": "[ READY  ]",
    "DRAFT":     "[ DRAFT  ]",
    "UPLOADED":  "[  LIVE  ]",
}


def badge(status: str) -> str:
    """Return a formatted status badge for terminal display."""
    key = status.upper().strip()
    if USE_COLOR:
        return STATUS_BADGES.get(key, f"{C.DIM}[ {key:^8} ]{C.RESET}")
    return STATUS_BADGES_PLAIN.get(key, f"[ {key:^8} ]")


# ─── Box drawing ──────────────────────────────────────────────────────────────

BOX_CHARS = {
    "tl": "╭", "tr": "╮", "bl": "╰", "br": "╯",
    "h": "─", "v": "│", "t": "┬", "b": "┴",
    "l": "├", "r": "┤", "x": "┼",
}


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes to compute visible width."""
    import re
    return re.sub(r"\033\[[0-9;]*m", "", text)


def _visible_len(text: str) -> int:
    return len(_strip_ansi(text))


def box_line(left: str = "│", content: str = "", right: str = "│", width: int | None = None) -> str:
    w = width or TERM_WIDTH
    vis = _visible_len(content)
    pad = max(0, w - vis - 4)
    return f"  {left} {content}{' ' * pad} {right}"


def box_top(width: int | None = None) -> str:
    w = width or TERM_WIDTH
    return f"  {BOX_CHARS['tl']}{BOX_CHARS['h'] * (w - 2)}{BOX_CHARS['tr']}"


def box_bottom(width: int | None = None) -> str:
    w = width or TERM_WIDTH
    return f"  {BOX_CHARS['bl']}{BOX_CHARS['h'] * (w - 2)}{BOX_CHARS['br']}"


def box_divider(width: int | None = None) -> str:
    w = width or TERM_WIDTH
    return f"  {BOX_CHARS['l']}{BOX_CHARS['h'] * (w - 2)}{BOX_CHARS['r']}"


# ─── Headers ──────────────────────────────────────────────────────────────────

def header(title: str, subtitle: str = "", emoji: str = "🧠") -> str:
    """Print a beautiful section header with optional subtitle."""
    w = TERM_WIDTH
    lines = [
        "",
        box_top(w),
        box_line(BOX_CHARS["v"], f"{C.BOLD}{C.CYAN}{emoji}  {title}{C.RESET}", BOX_CHARS["v"], w),
    ]
    if subtitle:
        lines.append(box_line(BOX_CHARS["v"], f"{C.DIM}{subtitle}{C.RESET}", BOX_CHARS["v"], w))
    lines.append(box_bottom(w))
    return "\n".join(lines)


def section(title: str, emoji: str = "📋") -> str:
    """Print a subsection divider."""
    return f"\n  {emoji} {C.BOLD}{C.WHITE}{title}{C.RESET}\n  {'─' * min(60, TERM_WIDTH - 4)}"


# ─── Progress bar ─────────────────────────────────────────────────────────────

def progress_bar(current: int, total: int, label: str = "", width: int = 30) -> str:
    """Render a Unicode progress bar."""
    if total <= 0:
        return ""
    ratio = min(1.0, current / total)
    filled = int(width * ratio)
    bar = "█" * filled + "░" * (width - filled)
    pct = int(ratio * 100)
    color = C.GREEN if pct >= 80 else (C.YELLOW if pct >= 40 else C.CYAN)
    suffix = f" {label}" if label else ""
    return f"  {color}{bar}{C.RESET} {C.BOLD}{pct:3d}%{C.RESET} ({current}/{total}){suffix}"


def scene_progress(scene_idx: int, total_scenes: int, scene_name: str = "", status: str = "") -> str:
    """Render a single scene progress line with status."""
    filled = "●" * scene_idx + "○" * (total_scenes - scene_idx)
    badge_str = badge(status) if status else ""
    name_str = f" {C.DIM}{scene_name}{C.RESET}" if scene_name else ""
    return f"  {C.CYAN}{filled}{C.RESET}  Scene {scene_idx}/{total_scenes}{name_str} {badge_str}"


# ─── Tables ───────────────────────────────────────────────────────────────────

def table(headers: List[str], rows: List[List[str]], col_widths: List[int] | None = None) -> str:
    """Render a formatted table with box-drawing characters."""
    if not rows:
        return "  (no data)"
    if not col_widths:
        col_widths = []
        for i, h in enumerate(headers):
            max_w = _visible_len(h)
            for row in rows:
                if i < len(row):
                    max_w = max(max_w, _visible_len(str(row[i])))
            col_widths.append(min(max_w + 2, 50))

    def _fmt_row(cells: List[str], sep: str = "│") -> str:
        columns = []
        for i, width in enumerate(col_widths):
            cell = str(cells[i]) if i < len(cells) else ""
            wrapped = []
            for line in cell.splitlines() or [""]:
                wrapped.extend(
                    [line] if _visible_len(line) <= width else
                    textwrap.wrap(_strip_ansi(line), width=width, drop_whitespace=False)
                )
            columns.append(wrapped)
        lines = []
        for line_idx in range(max(map(len, columns), default=1)):
            parts = []
            for width, column in zip(col_widths, columns):
                cell = column[line_idx] if line_idx < len(column) else ""
                parts.append(f" {cell}{' ' * (width - _visible_len(cell))}")
            lines.append(f"  {sep}{'│'.join(parts)}{sep}")
        return "\n".join(lines)

    def _rule(left: str, mid: str, right: str, fill: str = "─") -> str:
        segs = [fill * (cw + 1) for cw in col_widths]
        return f"  {left}{mid.join(segs)}{right}"

    lines = [
        _rule("┌", "┬", "┐"),
        _fmt_row([f"{C.BOLD}{h}{C.RESET}" for h in headers]),
        _rule("├", "┼", "┤"),
    ]
    for row in rows:
        lines.append(_fmt_row(row))
    lines.append(_rule("└", "┴", "┘"))
    return "\n".join(lines)


# ─── Agent Report Card ───────────────────────────────────────────────────────

def agent_report_card(reports: list) -> str:
    """Render a beautiful summary card for multi-agent execution reports.

    Expects a list of objects with attributes:
        agent_name, role, status, duration_s, summary, emoji (optional)
    """
    lines = [header("Multi-Agent Execution Report", "FrameForge Autonomous Crew v7.0", "🤖")]

    total_time = sum(getattr(r, "duration_s", 0) for r in reports)
    statuses = [str(getattr(r, "status", None) or "UNKNOWN").strip().upper() or "UNKNOWN" for r in reports]
    pass_count = sum(status in ("PASS", "HEALED") for status in statuses)
    warn_count = statuses.count("WARN")
    fail_count = statuses.count("FAIL")
    unknown_count = statuses.count("UNKNOWN")

    lines.append(section("Agent Results", "📊"))
    lines.append("")

    for i, r in enumerate(reports, 1):
        name = getattr(r, "agent_name", f"Agent {i}")
        role = getattr(r, "role", "Specialist")
        status = statuses[i - 1]
        dur = getattr(r, "duration_s", 0)
        summary = getattr(r, "summary", "")
        emoji = getattr(r, "emoji", "🤖")

        lines.append(f"  {badge(status)}  {C.BOLD}{emoji} {name}{C.RESET}")
        lines.append(f"           {C.DIM}{role}{C.RESET}")
        lines.append(f"           {C.GRAY}⏱ {dur:.2f}s{C.RESET}  {summary}")
        lines.append("")

    lines.append(section("Summary", "📈"))
    lines.append(f"  {C.GREEN}✅ {pass_count} passed{C.RESET}  "
                 f"{C.YELLOW}⚠️  {warn_count} warned{C.RESET}  "
                 f"{C.RED}❌ {fail_count} failed{C.RESET}  "
                 f"{C.GRAY}⏱ {total_time:.2f}s total{C.RESET}")
    if unknown_count:
        lines.append(f"  {unknown_count} unknown status")
    lines.append("")
    return "\n".join(lines)


# ─── Project Creation Card ────────────────────────────────────────────────────

def project_card(
    video_id: str,
    topic: str,
    genre: str,
    hook_score: int,
    hook_band: str,
    word_count: int,
    est_duration: float,
    scene_count: int,
    researchers: str = "",
    year: str = "",
    proj_path: str = "",
) -> str:
    """Render a beautiful project creation summary card."""
    w = TERM_WIDTH
    lines = [
        "",
        box_top(w),
        box_line(BOX_CHARS["v"], f"{C.BOLD}{C.CYAN}🎬  NEW PROJECT CREATED — {video_id}{C.RESET}", BOX_CHARS["v"], w),
        box_divider(w),
        box_line(BOX_CHARS["v"], f"{C.BOLD}Topic{C.RESET}       {topic}", BOX_CHARS["v"], w),
        box_line(BOX_CHARS["v"], f"{C.BOLD}Genre{C.RESET}       {genre}", BOX_CHARS["v"], w),
    ]
    if researchers and year:
        lines.append(box_line(BOX_CHARS["v"], f"{C.BOLD}Science{C.RESET}     {researchers} ({year})", BOX_CHARS["v"], w))
    lines.extend([
        box_divider(w),
        box_line(BOX_CHARS["v"], f"{C.BOLD}Hook Score{C.RESET}  {_hook_display(hook_score, hook_band)}", BOX_CHARS["v"], w),
        box_line(BOX_CHARS["v"], f"{C.BOLD}Pacing{C.RESET}      {word_count} words → ~{est_duration}s across {scene_count} scenes", BOX_CHARS["v"], w),
    ])
    if proj_path:
        lines.append(box_line(BOX_CHARS["v"], f"{C.BOLD}Saved{C.RESET}       {C.DIM}{proj_path}{C.RESET}", BOX_CHARS["v"], w))
    lines.append(box_bottom(w))
    lines.append("")
    return "\n".join(lines)


def _hook_display(score: int, band: str) -> str:
    """Colorized hook score display.

    The colour follows the band the scorer already printed, so this cannot disagree with
    hookscore.band() the way two sets of literals did (this file said 70, band() said 72).
    """
    color, icon = {"STRONG": (C.GREEN, "🔥"), "WORKABLE": (C.YELLOW, "⚡")}.get(band, (C.RED, "⚠️"))
    bar_len = 20
    filled = int(bar_len * score / 100)
    bar = "█" * filled + "░" * (bar_len - filled)
    return f"{icon} {color}{bar} {score}/100{C.RESET} [{band}]"


# ─── Verification Report ─────────────────────────────────────────────────────

def verification_header() -> str:
    return header("Pre-Upload Quality Gate", "Reference Precision & Recall Verification", "🛡️")


def verification_project_row(
    name: str,
    status: str,
    mp4_valid: bool = False,
    ref_precision: float = 0.0,
    duration_s: float = 0.0,
    bitrate_mbps: float = 0.0,
    issues: List[str] | None = None,
) -> str:
    """Render a single project verification result."""
    lines = []
    status = status.strip().upper()
    if not mp4_valid and status in {"PASS", "HEALED", "READY"}:
        status = "FAIL"
    status_badge = badge(status)
    valid_str = f"{C.GREEN}✓{C.RESET}" if mp4_valid else f"{C.RED}✗{C.RESET}"

    lines.append(
        f"  {status_badge}  {C.BOLD}{name}{C.RESET}"
        f"  │ MP4: {valid_str}"
        f"  │ Precision: {C.CYAN}{ref_precision:.3f}{C.RESET}"
        f"  │ {duration_s}s @ {bitrate_mbps} Mbps"
    )
    if issues:
        for issue in issues[:3]:
            lines.append(f"           {C.YELLOW}└─ {issue}{C.RESET}")
        if len(issues) > 3:
            lines.append(f"           {C.DIM}   ... and {len(issues) - 3} more{C.RESET}")
    return "\n".join(lines)


def verification_summary(passed: int, blueprints: int, warned: int, total: int,
                         drafts: int = 0) -> str:
    """Render verification summary line.

    drafts is only printed when non-zero, so a channel with no unbuilt projects reads exactly as it
    did before this status existed.
    """
    draft_part = f"{C.MAGENTA}📝 {drafts} never rendered{C.RESET}  " if drafts else ""
    return (
        f"\n  {C.BOLD}Summary{C.RESET}  "
        f"{C.GREEN}✅ {passed} passed{C.RESET}  "
        f"{C.BLUE}🔵 {blueprints} blueprint-ready{C.RESET}  "
        f"{draft_part}"
        f"{C.YELLOW}⚠️  {warned} warned{C.RESET}  "
        f"{C.DIM}({total} total){C.RESET}\n"
    )


# ─── Crew Status Display ─────────────────────────────────────────────────────

def crew_status(agents: list, personas: list[str] | None = None) -> str:
    """Render configured agents without assuming they have run or are online."""
    w = TERM_WIDTH
    lines = [
        "",
        box_top(w),
        box_line(BOX_CHARS["v"], f"{C.BOLD}{C.CYAN}🤖  FRAMEFORGE AUTONOMOUS MULTI-AGENT CREW{C.RESET}", BOX_CHARS["v"], w),
        box_line(BOX_CHARS["v"], f"{C.DIM}v7.0 — 3D Spatial & Semantic Prompt Edition{C.RESET}", BOX_CHARS["v"], w),
        box_divider(w),
    ]
    for idx, ag in enumerate(agents, 1):
        emoji = getattr(ag, "emoji", "🤖")
        name = getattr(ag, "name", f"Agent {idx}")
        role = getattr(ag, "role", "Specialist")
        lines.append(box_line(
            BOX_CHARS["v"],
            f"{C.BOLD}{idx}.{C.RESET} {emoji}  {C.CYAN}{name:<22}{C.RESET} {C.DIM}│{C.RESET} {role}",
            BOX_CHARS["v"],
            w,
        ))
    lines.append(box_divider(w))

    if personas:
        persona_str = ", ".join(personas)
        lines.append(box_line(BOX_CHARS["v"], f"{C.DIM}Personas: {persona_str}{C.RESET}", BOX_CHARS["v"], w))

    lines.append(box_line(
        BOX_CHARS["v"],
        f"{len(agents)} agents configured" if agents else "No agents configured",
        BOX_CHARS["v"],
        w,
    ))
    lines.append(box_bottom(w))
    lines.append("")
    return "\n".join(lines)


# ─── Skill Insight Tips ──────────────────────────────────────────────────────

def skill_tip(skill_name: str, insight: str, emoji: str = "💡") -> str:
    """Display a contextual skill insight or recommendation."""
    return f"  {emoji} {C.BOLD}{C.MAGENTA}{skill_name}{C.RESET}: {insight}"


# ─── Error / Warning / Info formatting ────────────────────────────────────────

def error(msg: str) -> str:
    return f"  {C.RED}{C.BOLD}✘ ERROR{C.RESET}  {msg}"


def warning(msg: str) -> str:
    return f"  {C.YELLOW}{C.BOLD}⚠ WARNING{C.RESET}  {msg}"


def info(msg: str) -> str:
    return f"  {C.CYAN}ℹ{C.RESET}  {msg}"


def success(msg: str) -> str:
    return f"  {C.GREEN}{C.BOLD}✔ {msg}{C.RESET}"


# ─── Voice.md buzzword sanitizer ──────────────────────────────────────────────

VOICE_BLACKLIST = [
    "delve", "tapestry", "testament", "landscape", "realm",
    "game-changer", "game changer", "unlock", "dive in",
    "let's dive in", "in this video", "mind-blowing", "insane",
    "crazy", "unbelievable", "revolutionary", "hey guys",
    "welcome back",
]


def sanitize_voice_text(text: str) -> str:
    """Strip AI buzzwords per voice.md blacklist and clean up results."""
    import re
    result = text
    for word in VOICE_BLACKLIST:
        pattern = r"\b" + re.escape(word) + r"\b"
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)
    result = re.sub(r"\s{2,}", " ", result)
    result = re.sub(r"\s*,\s*,+", ",", result)
    result = re.sub(r"\.\s*\.+", ".", result)
    return result.strip()


# ─── Convenience: print wrapper ───────────────────────────────────────────────

def emit(text: str) -> None:
    """Print formatted output to stdout."""
    print(text, flush=True)
