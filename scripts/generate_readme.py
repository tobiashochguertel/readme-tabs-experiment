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
generate_readme.py

Assembles README.md from the readme/ directory structure driven by readme/config.yaml.

Sections are rendered from:
  - Markdown files (sections/)
  - Tab group definitions (tab_groups in config.yaml → code files in readme/tabs/)
  - Animated SVG generation (delegated to generate_svg.py logic)
  - Summary table

Usage:
    ./scripts/generate_readme.py
    ./scripts/generate_readme.py --config readme/config.yaml --output README.md
    uv run scripts/generate_readme.py --dry-run

Author: Tobias Hochguertel
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer
import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from loguru import logger
from pydantic import BaseModel
from rich.console import Console

# ---------------------------------------------------------------------------
# Pydantic models for readme/config.yaml
# ---------------------------------------------------------------------------

app = typer.Typer(name="generate-readme", add_completion=False)
console = Console()
REPO_ROOT = Path(__file__).parent.parent


class TabItem(BaseModel):
    id: str
    label: str
    language: str | None = None
    source: str | None = None  # relative to REPO_ROOT
    image: str | None = None
    description: str | None = None


class TabGroup(BaseModel):
    title: str
    description: str = ""
    tabs: list[TabItem] = []


class Section(BaseModel):
    type: str
    anchor: str | None = None
    source: str | None = None
    tab_group: str | None = None
    output_svg: str | None = None


class ReadmeConfig(BaseModel):
    output: str = "README.md"
    sections: list[Section] = []


class PagesConfig(BaseModel):
    title: str = ""
    description: str = ""
    output_dir: str = "docs"


class ProjectConfig(BaseModel):
    name: str
    description: str
    github_pages_url: str | None = None
    repository: str | None = None


class Config(BaseModel):
    project: ProjectConfig
    readme: ReadmeConfig
    pages: PagesConfig = PagesConfig()
    tab_groups: dict[str, TabGroup] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_config(config_path: Path) -> Config:
    """Load and parse readme/config.yaml."""
    with config_path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Config.model_validate(raw)


def read_file(path: Path) -> str:
    """Read a text file, returning empty string if missing."""
    if not path.exists():
        logger.warning(f"File not found: {path}")
        return ""
    return path.read_text(encoding="utf-8")


def render_details_accordion(tab_group: TabGroup, root: Path) -> str:
    """Render a <details>/<summary> accordion for a tab group."""
    lines: list[str] = [
        f"## ① `<details>` / `<summary>` — Collapsible Accordion ✅\n",
        f"Best for **code blocks**: compact by default, fully copyable when expanded.\n",
    ]

    for tab in tab_group.tabs:
        if tab.source:
            content = read_file(root / tab.source)
            lang = tab.language or ""
            lines.append(f"\n<details>")
            lines.append(f"<summary>{tab.label}</summary>\n")
            lines.append(f"```{lang}")
            lines.append(content.rstrip())
            lines.append(f"```\n")
            lines.append(f"</details>\n")

    lines.append("\n---\n")
    return "\n".join(lines)


def render_html_table(tab_group: TabGroup, root: Path) -> str:
    """Render an HTML table of images with captions."""
    lines: list[str] = [
        f"## ② HTML `<table>` — Side-by-Side Gallery ✅\n",
        f"Best for **images**: shows them side-by-side with descriptions.\n",
        f"`<img>` `width` and `height` attributes are allowed by GitHub.\n",
    ]

    tabs = tab_group.tabs
    # Render 2 columns
    col_width = "50%"

    lines.append("\n<table>")
    lines.append("<tr>")
    for tab in tabs:
        lines.append(f"  <th>{tab.label}</th>")
    lines.append("</tr>")

    # Images row
    lines.append("<tr>")
    for tab in tabs:
        if tab.image:
            lines.append(f"  <td><img src=\"{tab.image}\" alt=\"{tab.label}\" width=\"400\"/></td>")
    lines.append("</tr>")

    # Description row
    lines.append("<tr>")
    for tab in tabs:
        desc = tab.description or ""
        lines.append(f"  <td>{desc}</td>")
    lines.append("</tr>")
    lines.append("</table>\n")

    lines.append("\n> **Tip:** Use `width` on `<img>` to keep columns balanced regardless of original resolution.\n")
    lines.append("\n---\n")
    return "\n".join(lines)


def render_animated_svg_section(output_svg: str, pages_url: str | None) -> str:
    """Render the section that references the animated SVG."""
    lines = [
        "## ③ Animated SVG — Auto-Cycling Visual Tabs ✅\n",
        "Pure SVG + CSS `@keyframes`. Cycles through panels automatically every ~4 s.",
        "Content is **not copy-pasteable** (rendered as an image), but great for visual demos.\n",
        f"![Auto-cycling code tabs]({output_svg})\n",
        "> GitHub strips `<foreignObject>` from SVGs, so content must be expressed as",
        "> native SVG elements (`<text>`, `<rect>`, etc.) — no HTML, no copy-paste.\n",
        "\n---\n",
    ]
    return "\n".join(lines)


def render_summary_table(pages_url: str | None) -> str:
    """Render the final summary table."""
    pages_link = f"[→ Live demo]({pages_url})" if pages_url else "—"
    return f"""## Summary

| Technique | Works on github.com? | Interactive? | Copy-paste? |
|---|---|---|---|
| `<details>/<summary>` | ✅ | Click to expand | ✅ |
| HTML `<table>` | ✅ | — | ✅ |
| Animated SVG | ✅ | Auto-cycle only | ❌ (image) |
| CSS radio-button tabs | ❌ | — | — |
| JS tabs | ❌ | — | — |
| GitHub Pages (HTML/JS) | — | ✅ fully interactive | ✅ |

**Recommendation:** Use `<details>` for code blocks and `<table>` for images on github.com.
For a full interactive experience, host on GitHub Pages.

{pages_link}
"""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


@app.command()
def main(
    config: Path = typer.Option(
        Path("readme/config.yaml"),
        "--config",
        "-c",
        help="Path to readme/config.yaml",
    ),
    output: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Output path (overrides config)",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print output without writing."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Generate README.md from the readme/ directory structure."""
    setup_logging(verbose)

    config_path = REPO_ROOT / config
    if not config_path.exists():
        logger.error(f"Config not found: {config_path}")
        sys.exit(1)

    cfg = load_config(config_path)
    output_path = REPO_ROOT / (str(output) if output else cfg.readme.output)
    pages_url = cfg.project.github_pages_url

    logger.info(f"Generating {output_path} from {config_path}")

    sections_output: list[str] = []

    for section in cfg.readme.sections:
        logger.debug(f"Rendering section type={section.type}")

        if section.type == "header" and section.source:
            sections_output.append(read_file(REPO_ROOT / "readme" / section.source))

        elif section.type == "details-accordion":
            grp_key = section.tab_group or ""
            grp = cfg.tab_groups.get(grp_key)
            if grp:
                sections_output.append(render_details_accordion(grp, REPO_ROOT / "readme"))
            else:
                logger.warning(f"Tab group not found: {grp_key}")

        elif section.type == "html-table":
            grp_key = section.tab_group or ""
            grp = cfg.tab_groups.get(grp_key)
            if grp:
                sections_output.append(render_html_table(grp, REPO_ROOT / "readme"))
            else:
                logger.warning(f"Tab group not found: {grp_key}")

        elif section.type == "animated-svg":
            svg_path = section.output_svg or "tabs-animated.svg"
            sections_output.append(render_animated_svg_section(svg_path, pages_url))
            # Also regenerate the SVG itself
            grp_key = section.tab_group or ""
            grp = cfg.tab_groups.get(grp_key)
            if grp:
                _regenerate_svg(grp, REPO_ROOT / svg_path, dry_run)

        elif section.type == "interactive-link" and section.source:
            sections_output.append(read_file(REPO_ROOT / "readme" / section.source))

        elif section.type == "summary-table":
            sections_output.append(render_summary_table(pages_url))

        else:
            logger.debug(f"Skipping unknown section type: {section.type}")

    readme_content = "\n".join(sections_output)

    if dry_run:
        console.print(readme_content)
        console.print(f"\n[dim]Dry run — not written to {output_path}[/dim]")
    else:
        output_path.write_text(readme_content, encoding="utf-8")
        console.print(f"[green]✓[/green] Written: {output_path}")


def _regenerate_svg(tab_group: TabGroup, svg_path: Path, dry_run: bool) -> None:
    """Regenerate the animated SVG by calling generate_svg.py as a subprocess."""
    import subprocess

    script = Path(__file__).parent / "generate_svg.py"
    if not script.exists():
        logger.warning("generate_svg.py not found — skipping SVG regeneration")
        return

    cmd = [
        "uv", "run", "--script", str(script),
        "--tab-group", "code-examples",
        "--output", str(svg_path),
    ]
    if dry_run:
        cmd.append("--dry-run")

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"SVG generation failed: {e}")


def setup_logging(verbose: bool) -> None:
    """Configure loguru for CLI use."""
    logger.remove()
    level = "DEBUG" if verbose else "WARNING"
    logger.add(sys.stderr, level=level)


if __name__ == "__main__":
    app()
