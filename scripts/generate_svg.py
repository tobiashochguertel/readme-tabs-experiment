#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pydantic>=2.0",
#     "pydantic-settings>=2.0",
#     "pyyaml>=6.0",
#     "jinja2>=3.0",
#     "typer>=0.12",
#     "rich>=13.0",
#     "loguru>=0.7",
# ]
# ///
"""
generate_svg.py

Generates tabs-animated.svg from tab group definitions in readme/config.yaml.
The SVG uses CSS @keyframes to auto-cycle through panels — works as <img> in GitHub READMEs.

Usage:
    ./scripts/generate_svg.py
    ./scripts/generate_svg.py --tab-group code-examples --output tabs-animated.svg
    uv run scripts/generate_svg.py --dry-run

Author: Tobias Hochguertel
"""

from __future__ import annotations

import sys
from pathlib import Path
from textwrap import indent
from xml.sax.saxutils import escape

import typer
import yaml
from loguru import logger
from pydantic import BaseModel
from rich.console import Console

app = typer.Typer(name="generate-svg", add_completion=False)
console = Console()
REPO_ROOT = Path(__file__).parent.parent

# --------------------------------------------------------------------------
# Syntax token colours (VS Code Dark+ palette)
# --------------------------------------------------------------------------
COLOUR = {
    "comment": "#6a9955",
    "keyword": "#569cd6",
    "fn":      "#dcdcaa",
    "string":  "#ce9178",
    "var":     "#9cdcfe",
    "num":     "#b5cea8",
    "type":    "#4ec9b0",
    "plain":   "#d4d4d4",
    "dim":     "#858585",
}

TAB_CYCLE_S = 4          # seconds per tab
PANEL_H    = 300         # height of code panel area
SVG_W      = 780
SVG_H      = 40 + PANEL_H  # tab bar + panel

# --------------------------------------------------------------------------
# Pydantic (re-used subset)
# --------------------------------------------------------------------------

class TabItem(BaseModel):
    id: str
    label: str
    language: str | None = None
    source: str | None = None
    image: str | None = None
    description: str | None = None


class TabGroup(BaseModel):
    title: str
    description: str = ""
    tabs: list[TabItem] = []


class Config(BaseModel):
    tab_groups: dict[str, TabGroup] = {}


# --------------------------------------------------------------------------
# SVG helpers
# --------------------------------------------------------------------------

def _css_keyframes(n: int, duration: int) -> str:
    """Build per-panel CSS animation keyframes for n panels."""
    step = 100.0 / n
    lines: list[str] = []

    for i in range(n):
        start = i * step
        end   = start + step
        # panel
        lines.append(f"    @keyframes show-{i+1} {{")
        if i == 0:
            lines.append(f"      0%,{end-0.1:.1f}%{{opacity:1}} {end:.1f}%,100%{{opacity:0}}")
        elif i == n - 1:
            lines.append(f"      0%,{start:.1f}%{{opacity:0}} {start+0.1:.1f}%,100%{{opacity:1}}")
        else:
            lines.append(
                f"      0%,{start:.1f}%{{opacity:0}} "
                f"{start+0.1:.1f}%,{end-0.1:.1f}%{{opacity:1}} "
                f"{end:.1f}%,100%{{opacity:0}}"
            )
        lines.append("    }")

        # tab active indicator
        lines.append(f"    @keyframes tab-active-{i+1} {{")
        if i == 0:
            lines.append(f"      0%,{end-0.1:.1f}%{{fill:#2563eb}} {end:.1f}%,100%{{fill:#334155}}")
        elif i == n - 1:
            lines.append(f"      0%,{start:.1f}%{{fill:#334155}} {start+0.1:.1f}%,100%{{fill:#2563eb}}")
        else:
            lines.append(
                f"      0%,{start:.1f}%{{fill:#334155}} "
                f"{start+0.1:.1f}%,{end-0.1:.1f}%{{fill:#2563eb}} "
                f"{end:.1f}%,100%{{fill:#334155}}"
            )
        lines.append("    }")

        # tab text colour
        lines.append(f"    @keyframes tabtxt-{i+1} {{")
        if i == 0:
            lines.append(f"      0%,{end-0.1:.1f}%{{fill:#fff}} {end:.1f}%,100%{{fill:#94a3b8}}")
        elif i == n - 1:
            lines.append(f"      0%,{start:.1f}%{{fill:#94a3b8}} {start+0.1:.1f}%,100%{{fill:#fff}}")
        else:
            lines.append(
                f"      0%,{start:.1f}%{{fill:#94a3b8}} "
                f"{start+0.1:.1f}%,{end-0.1:.1f}%{{fill:#fff}} "
                f"{end:.1f}%,100%{{fill:#94a3b8}}"
            )
        lines.append("    }")

    return "\n".join(lines)


def _tokenize_code(source: str, language: str | None) -> list[tuple[str, str]]:
    """
    Very lightweight tokenizer — returns list of (colour_hex, text) spans.
    Each span is a single line; the caller adds line-breaks between them.
    """
    if language in ("python", "py"):
        return _tok_python(source)
    if language in ("javascript", "js", "typescript", "ts"):
        return _tok_js(source)
    if language == "go":
        return _tok_go(source)
    if language in ("rust", "rs"):
        return _tok_rust(source)
    # fallback: plain
    return [(COLOUR["plain"], line) for line in source.splitlines()]


def _simple_highlight(line: str, keywords: set[str], comment_prefix: str) -> list[tuple[str, str]]:
    """Return list of (colour, word) for a single line with simple rules."""
    stripped = line.lstrip()
    indent_ws = line[: len(line) - len(stripped)]
    spans: list[tuple[str, str]] = []
    if indent_ws:
        spans.append((COLOUR["plain"], indent_ws))

    if stripped.startswith(comment_prefix):
        spans.append((COLOUR["comment"], stripped))
        return spans

    for word in stripped.split():
        clean = word.rstrip("(:{,")
        if clean in keywords:
            spans.append((COLOUR["keyword"], word + " "))
        elif word.startswith('"') or word.startswith("'") or word.startswith('`'):
            spans.append((COLOUR["string"], word + " "))
        else:
            spans.append((COLOUR["plain"], word + " "))
    return spans


def _tok_python(source: str) -> list[tuple[str, str]]:
    kw = {"def", "class", "return", "import", "from", "if", "else", "elif",
          "while", "for", "in", "and", "or", "not", "True", "False", "None",
          "with", "as", "raise", "try", "except", "finally", "pass", "yield",
          "lambda", "global", "nonlocal", "del", "assert", "break", "continue"}
    result = []
    for line in source.splitlines():
        for colour, text in _simple_highlight(line, kw, "#"):
            result.append((colour, text))
        result.append((COLOUR["plain"], "\n"))
    return result


def _tok_js(source: str) -> list[tuple[str, str]]:
    kw = {"function", "const", "let", "var", "return", "if", "else", "while",
          "for", "of", "in", "new", "class", "import", "export", "from",
          "async", "await", "true", "false", "null", "undefined"}
    result = []
    for line in source.splitlines():
        for colour, text in _simple_highlight(line, kw, "//"):
            result.append((colour, text))
        result.append((COLOUR["plain"], "\n"))
    return result


def _tok_go(source: str) -> list[tuple[str, str]]:
    kw = {"package", "import", "func", "return", "for", "if", "else", "var",
          "const", "type", "struct", "interface", "go", "defer", "chan",
          "select", "case", "default", "break", "continue", "range", "make",
          "append", "len", "cap", "nil", "true", "false"}
    result = []
    for line in source.splitlines():
        for colour, text in _simple_highlight(line, kw, "//"):
            result.append((colour, text))
        result.append((COLOUR["plain"], "\n"))
    return result


def _tok_rust(source: str) -> list[tuple[str, str]]:
    kw = {"fn", "let", "mut", "pub", "struct", "impl", "trait", "for", "in",
          "while", "if", "else", "return", "use", "mod", "crate", "self",
          "super", "match", "enum", "where", "type", "const", "static",
          "async", "await", "move", "ref", "dyn", "true", "false", "Vec",
          "Option", "Result", "Some", "None", "Ok", "Err"}
    result = []
    for line in source.splitlines():
        for colour, text in _simple_highlight(line, kw, "//"):
            result.append((colour, text))
        result.append((COLOUR["plain"], "\n"))
    return result


def _render_code_panel(source: str, language: str | None) -> str:
    """Render syntax-highlighted code as SVG <tspan> elements."""
    spans = _tokenize_code(source, language)
    x, y = 20, 70
    line_h = 18
    svg_lines: list[str] = []
    current_line_spans: list[str] = []

    for colour, text in spans:
        if text == "\n":
            if current_line_spans:
                svg_lines.append(
                    f'      <text x="{x}" y="{y}" font-family="ui-monospace,monospace" font-size="12" xml:space="preserve">{"".join(current_line_spans)}</text>'
                )
                current_line_spans = []
            y += line_h
            if y > SVG_H - 20:
                break
        else:
            safe = escape(text)
            current_line_spans.append(f'<tspan fill="{colour}">{safe}</tspan>')

    return "\n".join(svg_lines)


def build_animated_svg(tab_group: TabGroup, output_path: Path, dry_run: bool, root: Path = REPO_ROOT) -> None:
    """Build the animated SVG file from a tab group."""
    tabs = tab_group.tabs
    n = len(tabs)
    duration = TAB_CYCLE_S * n

    tab_w = min(160, SVG_W // max(n, 1))

    keyframes = _css_keyframes(n, duration)

    panel_animations = "\n    ".join(
        f".panel-{i+1} {{ animation: show-{i+1} {duration}s step-start infinite; }}"
        for i in range(n)
    )
    tab_bg_animations = "\n    ".join(
        f".tab-bg-{i+1} {{ animation: tab-active-{i+1} {duration}s step-start infinite; }}"
        for i in range(n)
    )
    tab_txt_animations = "\n    ".join(
        f".tab-txt-{i+1} {{ animation: tabtxt-{i+1} {duration}s step-start infinite; }}"
        for i in range(n)
    )

    # Tab bar
    tab_rects: list[str] = []
    tab_texts: list[str] = []
    for i, tab in enumerate(tabs):
        x = i * tab_w + 8
        cx = x + tab_w // 2 - 4
        tab_rects.append(f'  <rect class="tab-bg-{i+1}" x="{x}" y="6" width="{tab_w-4}" height="28" rx="5"/>')
        tab_texts.append(f'  <text class="label tab-txt-{i+1}" x="{cx}" y="24" text-anchor="middle">{escape(tab.label)}</text>')

    # Panels
    panels: list[str] = []
    for i, tab in enumerate(tabs):
        code = ""
        if tab.source:
            src_path = root / "readme" / tab.source
            if src_path.exists():
                code = src_path.read_text(encoding="utf-8")
            else:
                logger.warning(f"Source not found: {src_path}")
        panel_content = _render_code_panel(code, tab.language)
        panels.append(
            f'  <g class="panel panel-{i+1}" opacity="0">\n'
            f'    <rect x="0" y="42" width="{SVG_W}" height="{PANEL_H}" fill="#1e1e1e"/>\n'
            f"{panel_content}\n"
            f"  </g>"
        )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SVG_W} {SVG_H}" width="{SVG_W}" height="{SVG_H}">
  <style>
    .panel {{ opacity: 0; }}
    {panel_animations}
    {tab_bg_animations}
    {tab_txt_animations}
{keyframes}
    text {{ font-family: ui-monospace, "Cascadia Code", "Fira Code", monospace; font-size: 12px; }}
    .label {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; font-size: 12px; }}
    .dim {{ fill: #858585; }}
  </style>

  <!-- Card -->
  <rect width="{SVG_W}" height="{SVG_H}" rx="8" fill="#1e1e1e"/>
  <!-- Tab bar -->
  <rect x="0" y="0" width="{SVG_W}" height="42" rx="8" fill="#252526"/>
  <rect x="0" y="32" width="{SVG_W}" height="10" fill="#252526"/>

{"".join(chr(10) + r for r in tab_rects)}
{"".join(chr(10) + t for t in tab_texts)}
  <text class="label dim" x="{SVG_W - 10}" y="{SVG_H - 8}" text-anchor="end">auto-cycling every {TAB_CYCLE_S}s</text>

{"".join(chr(10) + p for p in panels)}
</svg>
"""

    if dry_run:
        console.print(svg[:500] + "\n…[truncated]")
        console.print(f"[dim]Dry run — not written to {output_path}[/dim]")
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(svg, encoding="utf-8")
        console.print(f"[green]✓[/green] SVG written: {output_path}")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


@app.command()
def main(
    config: Path = typer.Option(
        Path("readme/config.yaml"),
        "--config",
        "-c",
        help="Path to readme/config.yaml",
    ),
    tab_group: str = typer.Option(
        "code-examples",
        "--tab-group",
        "-g",
        help="Tab group key to render",
    ),
    output: Path = typer.Option(
        Path("tabs-animated.svg"),
        "--output",
        "-o",
        help="Output SVG path",
    ),
    dry_run: bool = typer.Option(False, "--dry-run"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Generate an auto-cycling animated SVG from a tab group in readme/config.yaml."""
    _setup_logging(verbose)

    config_path = REPO_ROOT / config
    if not config_path.exists():
        logger.error(f"Config not found: {config_path}")
        sys.exit(1)

    with config_path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    cfg = Config.model_validate(raw)

    grp = cfg.tab_groups.get(tab_group)
    if grp is None:
        logger.error(f"Tab group '{tab_group}' not found in config")
        sys.exit(1)

    build_animated_svg(grp, REPO_ROOT / output, dry_run)


def _setup_logging(verbose: bool) -> None:
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "WARNING")


if __name__ == "__main__":
    app()
