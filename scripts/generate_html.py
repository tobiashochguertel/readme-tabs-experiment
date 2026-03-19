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
generate_html.py

Generates the GitHub Pages site (docs/index.html) and an interactive SVG (docs/interactive-tabs.svg)
from readme/config.yaml.

The HTML page provides fully interactive tabs (CSS + JS) for both code examples and screenshot
gallery. The interactive SVG uses <foreignObject> + CSS radio-button hack and works when opened
directly in a browser (not as an <img> in GitHub README).

Usage:
    ./scripts/generate_html.py
    uv run scripts/generate_html.py --dry-run

Author: Tobias Hochguertel
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer
import yaml
from jinja2 import Environment
from loguru import logger
from pydantic import BaseModel
from rich.console import Console

app = typer.Typer(name="generate-html", add_completion=False)
console = Console()
REPO_ROOT = Path(__file__).parent.parent


# --------------------------------------------------------------------------
# Pydantic models (subset)
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


class PagesConfig(BaseModel):
    title: str = "README Tabs Experiment"
    description: str = ""
    output_dir: str = "docs"
    theme: dict = {}


class ProjectConfig(BaseModel):
    name: str
    description: str
    github_pages_url: str | None = None
    repository: str | None = None


class Config(BaseModel):
    project: ProjectConfig
    pages: PagesConfig = PagesConfig()
    tab_groups: dict[str, TabGroup] = {}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def load_config(config_path: Path) -> Config:
    with config_path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Config.model_validate(raw)


def read_tab_content(tab: TabItem, root: Path) -> str:
    if tab.source:
        p = root / "readme" / tab.source
        if p.exists():
            return p.read_text(encoding="utf-8")
    return ""


# --------------------------------------------------------------------------
# HTML generation
# --------------------------------------------------------------------------

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{{ project.name }} — GitHub Pages Demo</title>
  <style>
    :root {
      --bg: #0d1117;
      --surface: #161b22;
      --surface2: #21262d;
      --border: #30363d;
      --text: #e6edf3;
      --muted: #8b949e;
      --primary: #2563eb;
      --primary-hover: #1d4ed8;
      --code-bg: #1e1e1e;
      --tab-radius: 8px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
      padding: 2rem;
    }
    header {
      max-width: 900px;
      margin: 0 auto 3rem;
      border-bottom: 1px solid var(--border);
      padding-bottom: 1.5rem;
    }
    header h1 { font-size: 2rem; margin-bottom: .5rem; }
    header p { color: var(--muted); }
    header a { color: var(--primary); text-decoration: none; }
    header a:hover { text-decoration: underline; }
    main { max-width: 900px; margin: 0 auto; }
    section { margin-bottom: 3rem; }
    h2 { font-size: 1.4rem; margin-bottom: 1rem; padding-bottom: .5rem; border-bottom: 1px solid var(--border); }
    h3 { font-size: 1.1rem; color: var(--muted); margin-bottom: .75rem; }
    p  { color: var(--muted); margin-bottom: 1rem; }

    /* ── TABS ── */
    .tab-widget { background: var(--surface); border: 1px solid var(--border); border-radius: var(--tab-radius); overflow: hidden; }
    .tab-widget input[type=radio] { display: none; }
    .tab-bar { display: flex; background: var(--surface2); border-bottom: 1px solid var(--border); gap: 4px; padding: 6px 6px 0; }
    .tab-bar label {
      padding: 8px 18px;
      border-radius: 6px 6px 0 0;
      cursor: pointer;
      color: var(--muted);
      font-size: .9rem;
      font-weight: 500;
      transition: background .15s, color .15s;
      border: 1px solid transparent;
      border-bottom: none;
      user-select: none;
    }
    .tab-bar label:hover { background: var(--border); color: var(--text); }
    .tab-panels { padding: 0; }
    .tab-panel { display: none; }

{% for group_key, group in tab_groups.items() %}
{% for tab in group.tabs %}
    #{{ group_key }}-{{ tab.id }}:checked ~ .tab-bar label[for="{{ group_key }}-{{ tab.id }}"] {
      background: var(--primary); color: #fff; border-color: var(--border);
    }
    #{{ group_key }}-{{ tab.id }}:checked ~ .tab-panels .panel-{{ tab.id }} { display: block; }
{% endfor %}
{% endfor %}

    /* ── CODE ── */
    pre {
      background: var(--code-bg);
      padding: 1.25rem 1.5rem;
      overflow-x: auto;
      font-family: "Fira Code", "Cascadia Code", ui-monospace, monospace;
      font-size: .85rem;
      line-height: 1.6;
      margin: 0;
    }
    code { font-family: inherit; }

    /* ── GALLERY ── */
    .gallery-img { max-width: 100%; display: block; border-radius: 4px; }
    .img-caption  { padding: 1rem 1.25rem; color: var(--muted); font-size: .9rem; }

    /* ── TECHNIQUE TABLE ── */
    table { width: 100%; border-collapse: collapse; font-size: .9rem; }
    th, td { padding: .6rem 1rem; text-align: left; border-bottom: 1px solid var(--border); }
    th { background: var(--surface2); color: var(--text); }
    td { color: var(--muted); }
    .yes { color: #3fb950; }
    .no  { color: #f85149; }

    /* ── INTERACTIVE SVG SECTION ── */
    .svg-link-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--tab-radius);
      padding: 1.5rem;
    }
    .svg-link-card a { color: var(--primary); font-size: 1rem; font-weight: 600; }
    .svg-link-card p { margin-top: .5rem; font-size: .85rem; }

    footer { margin-top: 4rem; padding-top: 1rem; border-top: 1px solid var(--border); color: var(--muted); font-size: .8rem; text-align: center; }
    footer a { color: var(--primary); }
  </style>
</head>
<body>
<header>
  <h1>{{ project.name }}</h1>
  <p>{{ project.description }}</p>
  <p style="margin-top:.5rem">
    <a href="https://github.com/{{ project.repository }}">GitHub Repository</a> ·
    <a href="https://github.com/{{ project.repository }}/blob/main/README.md">README.md source</a>
  </p>
</header>

<main>

  <!-- ① details / summary -->
  <section id="details-accordion">
    <h2>① <code>&lt;details&gt;</code> / <code>&lt;summary&gt;</code> — Collapsible Accordion</h2>
    <p>Works directly on github.com — click to expand, content is fully copyable.</p>
    <div style="display:flex;flex-direction:column;gap:.5rem">
{% for tab in tab_groups['code-examples'].tabs %}
      <details style="background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:.75rem 1rem">
        <summary style="cursor:pointer;font-weight:600;list-style:none;display:flex;align-items:center;gap:.5rem">
          {{ tab.label }}
        </summary>
        <pre><code class="language-{{ tab.language }}">{{ tab_contents['code-examples'][tab.id] | e }}</code></pre>
      </details>
{% endfor %}
    </div>
  </section>

  <!-- ② CSS radio-button tabs (code) -->
  <section id="css-tabs">
    <h2>② CSS Radio-Button Tabs — Code Examples <span style="color:#3fb950;font-size:.8em">✅ interactive here</span></h2>
    <p>This technique requires <code>&lt;style&gt;</code> — stripped on github.com, works here.</p>
    <div class="tab-widget">
{% for tab in tab_groups['code-examples'].tabs %}
      <input type="radio" id="code-examples-{{ tab.id }}" name="code-examples"{% if loop.first %} checked{% endif %}>
{% endfor %}
      <div class="tab-bar">
{% for tab in tab_groups['code-examples'].tabs %}
        <label for="code-examples-{{ tab.id }}">{{ tab.label }}</label>
{% endfor %}
      </div>
      <div class="tab-panels">
{% for tab in tab_groups['code-examples'].tabs %}
        <div class="tab-panel panel-{{ tab.id }}">
          <pre><code>{{ tab_contents['code-examples'][tab.id] | e }}</code></pre>
        </div>
{% endfor %}
      </div>
    </div>
  </section>

  <!-- ③ Screenshot gallery tabs -->
  <section id="screenshot-tabs">
    <h2>③ Screenshot Gallery Tabs <span style="color:#3fb950;font-size:.8em">✅ interactive here</span></h2>
    <p>Taskbook CLI screenshots shown in interactive tabs — impossible on github.com without JS/CSS.</p>
    <div class="tab-widget">
{% for tab in tab_groups['screenshots'].tabs %}
      <input type="radio" id="screenshots-{{ tab.id }}" name="screenshots"{% if loop.first %} checked{% endif %}>
{% endfor %}
      <div class="tab-bar">
{% for tab in tab_groups['screenshots'].tabs %}
        <label for="screenshots-{{ tab.id }}">{{ tab.label }}</label>
{% endfor %}
      </div>
      <div class="tab-panels">
{% for tab in tab_groups['screenshots'].tabs %}
        <div class="tab-panel panel-{{ tab.id }}">
          <img class="gallery-img" src="{{ tab.image }}" alt="{{ tab.label }}"/>
          <p class="img-caption">{{ tab.description }}</p>
        </div>
{% endfor %}
      </div>
    </div>
  </section>

  <!-- ④ Interactive SVG -->
  <section id="interactive-svg">
    <h2>④ Interactive SVG via <code>&lt;foreignObject&gt;</code></h2>
    <p>
      An SVG file with embedded HTML+CSS. Works when opened directly in a browser.
      GitHub strips <code>&lt;foreignObject&gt;</code> when rendering SVGs via <code>&lt;img&gt;</code> tags.
    </p>
    <div class="svg-link-card">
      <a href="interactive-tabs.svg" target="_blank">→ Open interactive-tabs.svg directly</a>
      <p>Click the link above to open the SVG in a new tab. The tabs are fully clickable.</p>
    </div>
    <br/>
    <p>Also try the animated version (works as a GitHub README <code>&lt;img&gt;</code>):</p>
    <img src="animated-preview.svg" alt="Animated tabs" style="max-width:100%;border-radius:8px"/>
  </section>

  <!-- Summary table -->
  <section id="summary">
    <h2>Summary</h2>
    <table>
      <tr><th>Technique</th><th>github.com</th><th>GitHub Pages</th><th>Copy-paste</th></tr>
      <tr><td><code>&lt;details&gt;/&lt;summary&gt;</code></td><td class="yes">✅</td><td class="yes">✅</td><td class="yes">✅</td></tr>
      <tr><td>HTML <code>&lt;table&gt;</code></td><td class="yes">✅</td><td class="yes">✅</td><td class="yes">✅</td></tr>
      <tr><td>Animated SVG</td><td class="yes">✅</td><td class="yes">✅</td><td class="no">❌</td></tr>
      <tr><td>CSS radio-button tabs</td><td class="no">❌</td><td class="yes">✅</td><td class="yes">✅</td></tr>
      <tr><td>JS tabs</td><td class="no">❌</td><td class="yes">✅</td><td class="yes">✅</td></tr>
      <tr><td>SVG <code>&lt;foreignObject&gt;</code></td><td class="no">❌ stripped</td><td class="yes">✅</td><td class="yes">✅</td></tr>
    </table>
  </section>

</main>

<footer>
  <a href="https://github.com/{{ project.repository }}">tobiashochguertel/readme-tabs-experiment</a>
  · Generated by <code>scripts/generate_html.py</code>
</footer>
</body>
</html>
"""

# --------------------------------------------------------------------------
# Interactive SVG template (foreignObject + CSS radio-button tabs)
# --------------------------------------------------------------------------

INTERACTIVE_SVG_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<!-- Interactive SVG — works when opened directly in a browser, NOT as <img> -->
<!-- GitHub strips <foreignObject> when rendering via <img> tags -->
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xhtml="http://www.w3.org/1999/xhtml"
     viewBox="0 0 820 520" width="820" height="520">
  <foreignObject width="820" height="520">
    <xhtml:div>
      <xhtml:style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        body, div.root {
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background: #0d1117;
          color: #e6edf3;
          width: 820px;
          height: 520px;
          overflow: hidden;
        }
        h3 { font-size: 1rem; padding: .75rem 1rem .25rem; color: #8b949e; }
        /* Radio inputs hidden */
        input[type=radio] { display: none; }
        /* Tab bar */
        .tab-bar { display: flex; background: #21262d; border-bottom: 1px solid #30363d; gap: 4px; padding: 6px 6px 0; }
        .tab-bar label {
          padding: 7px 16px;
          border-radius: 6px 6px 0 0;
          cursor: pointer;
          color: #8b949e;
          font-size: .85rem;
          font-weight: 500;
          border: 1px solid transparent;
          border-bottom: none;
          transition: background .1s;
        }
        .tab-bar label:hover { background: #30363d; color: #e6edf3; }
        /* Panels */
        .tab-panel { display: none; }
        pre {
          background: #1e1e1e;
          padding: 1rem 1.25rem;
          font-family: "Fira Code", "Cascadia Code", ui-monospace, monospace;
          font-size: .8rem;
          line-height: 1.6;
          overflow: auto;
          height: 400px;
          margin: 0;
        }
        /* Active tab per group */
{% for tab in tabs %}
        #itab-{{ tab.id }}:checked ~ .tab-bar label[for="itab-{{ tab.id }}"] {
          background: #2563eb; color: #fff; border-color: #30363d;
        }
        #itab-{{ tab.id }}:checked ~ .tab-panels .panel-{{ tab.id }} { display: block; }
{% endfor %}
      </xhtml:style>
      <xhtml:div class="root">
        <xhtml:h3>💡 Click a tab — this SVG uses CSS radio-button tabs via &lt;foreignObject&gt;</xhtml:h3>
{% for tab in tabs %}
        <xhtml:input type="radio" id="itab-{{ tab.id }}" name="itabs"{% if loop.first %} checked="checked"{% endif %}/>
{% endfor %}
        <xhtml:div class="tab-bar">
{% for tab in tabs %}
          <xhtml:label for="itab-{{ tab.id }}">{{ tab.label }}</xhtml:label>
{% endfor %}
        </xhtml:div>
        <xhtml:div class="tab-panels">
{% for tab in tabs %}
          <xhtml:div class="tab-panel panel-{{ tab.id }}">
            <xhtml:pre>{{ tab_contents[tab.id] | e }}</xhtml:pre>
          </xhtml:div>
{% endfor %}
        </xhtml:div>
      </xhtml:div>
    </xhtml:div>
  </foreignObject>
</svg>
"""


# --------------------------------------------------------------------------
# Build functions
# --------------------------------------------------------------------------

def build_html(cfg: Config, root: Path) -> str:
    """Render docs/index.html from the Jinja2 template."""
    env = Environment(autoescape=False)
    tmpl = env.from_string(HTML_TEMPLATE)

    # Pre-load all tab file contents
    tab_contents: dict[str, dict[str, str]] = {}
    for grp_key, grp in cfg.tab_groups.items():
        tab_contents[grp_key] = {}
        for tab in grp.tabs:
            content = ""
            if tab.source:
                p = root / "readme" / tab.source
                content = p.read_text(encoding="utf-8") if p.exists() else f"# file not found: {tab.source}"
            tab_contents[grp_key][tab.id] = content

    return tmpl.render(
        project=cfg.project,
        pages=cfg.pages,
        tab_groups=cfg.tab_groups,
        tab_contents=tab_contents,
    )


def build_interactive_svg(cfg: Config, root: Path) -> str:
    """Render docs/interactive-tabs.svg for the code-examples group."""
    env = Environment(autoescape=False)
    tmpl = env.from_string(INTERACTIVE_SVG_TEMPLATE)

    grp = cfg.tab_groups.get("code-examples")
    if grp is None:
        return "<!-- no code-examples tab group -->"

    tab_contents: dict[str, str] = {}
    for tab in grp.tabs:
        content = ""
        if tab.source:
            p = root / "readme" / tab.source
            content = p.read_text(encoding="utf-8") if p.exists() else f"# not found: {tab.source}"
        tab_contents[tab.id] = content

    return tmpl.render(tabs=grp.tabs, tab_contents=tab_contents)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

@app.command()
def main(
    config: Path = typer.Option(Path("readme/config.yaml"), "--config", "-c"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Generate GitHub Pages site (docs/index.html + docs/interactive-tabs.svg)."""
    _setup_logging(verbose)

    config_path = REPO_ROOT / config
    if not config_path.exists():
        logger.error(f"Config not found: {config_path}")
        sys.exit(1)

    with config_path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    cfg = Config.model_validate(raw)

    output_dir = REPO_ROOT / cfg.pages.output_dir

    html_content = build_html(cfg, REPO_ROOT)
    svg_content  = build_interactive_svg(cfg, REPO_ROOT)

    if dry_run:
        console.print(html_content[:400] + "\n…[truncated HTML]")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "index.html").write_text(html_content, encoding="utf-8")
    console.print(f"[green]✓[/green] {output_dir / 'index.html'}")

    (output_dir / "interactive-tabs.svg").write_text(svg_content, encoding="utf-8")
    console.print(f"[green]✓[/green] {output_dir / 'interactive-tabs.svg'}")

    (output_dir / ".nojekyll").write_text("", encoding="utf-8")
    console.print(f"[green]✓[/green] {output_dir / '.nojekyll'}")


def _setup_logging(verbose: bool) -> None:
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "WARNING")


if __name__ == "__main__":
    app()
