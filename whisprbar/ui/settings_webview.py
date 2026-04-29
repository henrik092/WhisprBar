"""Experimental WebKit settings window for WhisprBar.

This module is intentionally parallel to the production GTK 3 settings dialog.
It lets us evaluate a more modern HTML/CSS settings surface without changing
the existing save path yet.
"""

from __future__ import annotations

from html import escape
from typing import Iterable, Mapping, Optional

from whisprbar.flow.dictionary import load_dictionary
from whisprbar.flow.models import DictionaryEntry, Snippet
from whisprbar.flow.snippets import load_snippets
from whisprbar.utils import APP_NAME, notify


def _checked(value: object) -> str:
    return " checked" if bool(value) else ""


def _option(value: str, label: str, active_value: object) -> str:
    selected = " selected" if str(active_value) == value else ""
    return f'<option value="{escape(value)}"{selected}>{escape(label)}</option>'


def _switch(name: str, label: str, description: str, active: object) -> str:
    return f"""
      <label class="wb-row">
        <span class="wb-row-label">
          <b>{escape(label)}</b>
          <span>{escape(description)}</span>
        </span>
        <input class="wb-switch-input" type="checkbox" name="{escape(name)}"{_checked(active)}>
      </label>
    """


def _select(name: str, label: str, description: str, options: Iterable[tuple[str, str]], active: object) -> str:
    option_html = "\n".join(_option(value, text, active) for value, text in options)
    return f"""
      <label class="wb-row">
        <span class="wb-row-label">
          <b>{escape(label)}</b>
          <span>{escape(description)}</span>
        </span>
        <select name="{escape(name)}">{option_html}</select>
      </label>
    """


def _field(name: str, label: str, description: str, value: object, input_type: str = "text") -> str:
    return f"""
      <label class="wb-row">
        <span class="wb-row-label">
          <b>{escape(label)}</b>
          <span>{escape(description)}</span>
        </span>
        <input type="{escape(input_type)}" name="{escape(name)}" value="{escape(str(value or ''))}">
      </label>
    """


def _section(title: str, helper: str, rows: str, hero: bool = False) -> str:
    hero_class = " wb-hero" if hero else ""
    return f"""
      <section class="wb-section{hero_class}">
        <div class="wb-section-head">
          <h3>{escape(title)}</h3>
          <span>{escape(helper)}</span>
        </div>
        {rows}
      </section>
    """


def _dictionary_rows(dictionary_entries: Iterable[DictionaryEntry]) -> str:
    rows = []
    for entry in dictionary_entries:
        rows.append(
            """
            <div class="wb-table-row">
              <input value="{spoken}">
              <input value="{written}">
              <button type="button">-</button>
            </div>
            """.format(
                spoken=escape(entry.spoken),
                written=escape(entry.written),
            )
        )
    if not rows:
        rows.append(
            """
            <div class="wb-table-row">
              <input placeholder="whisper bar">
              <input placeholder="WhisprBar">
              <button type="button">-</button>
            </div>
            """
        )
    return "\n".join(rows)


def _snippet_rows(snippets: Iterable[Snippet]) -> str:
    rows = []
    for snippet in snippets:
        rows.append(
            """
            <div class="wb-table-row">
              <input value="{trigger}">
              <input value="{text}">
              <button type="button">-</button>
            </div>
            """.format(
                trigger=escape(snippet.trigger),
                text=escape(snippet.text),
            )
        )
    if not rows:
        rows.append(
            """
            <div class="wb-table-row">
              <input placeholder="my signature">
              <input placeholder="Best regards, Rik">
              <button type="button">-</button>
            </div>
            """
        )
    return "\n".join(rows)


def generate_settings_html(
    config: Mapping[str, object],
    dictionary_entries: Iterable[DictionaryEntry],
    snippets: Iterable[Snippet],
) -> str:
    """Generate the experimental WebKit settings HTML."""

    dictionary_rows = _dictionary_rows(dictionary_entries)
    snippet_rows = _snippet_rows(snippets)
    preferred_languages = config.get("flow_preferred_languages", ["de", "en"])
    if isinstance(preferred_languages, (list, tuple)):
        preferred_languages_text = ", ".join(str(item) for item in preferred_languages)
    else:
        preferred_languages_text = str(preferred_languages or "")

    general_rows = (
        _select(
            "theme_preference",
            "Theme",
            "Farbmodus der Bedienoberfläche.",
            [("auto", "Auto"), ("light", "Light"), ("dark", "Dark")],
            config.get("theme_preference", "auto"),
        )
        + _select(
            "language",
            "Language",
            "Primäre Sprache für die Transkription.",
            [("de", "Deutsch"), ("en", "English")],
            config.get("language", "de"),
        )
        + _switch(
            "auto_paste_enabled",
            "Auto-Paste",
            "Fügt Transkripte nach der Aufnahme automatisch ein.",
            config.get("auto_paste_enabled", False),
        )
        + _switch(
            "notifications_enabled",
            "Notifications",
            "Zeigt Desktop-Benachrichtigungen für Status und Fehler.",
            config.get("notifications_enabled", True),
        )
    )

    recording_rows = (
        _switch(
            "use_vad",
            "VAD",
            "Schneidet Stille und kann Aufnahmen kompakter machen.",
            config.get("use_vad", False),
        )
        + _field(
            "vad_bridge_ms",
            "Pause bridge",
            "Kurze Pausen werden weiter als ein Satz behandelt.",
            config.get("vad_bridge_ms", 180),
            "number",
        )
        + _switch(
            "noise_reduction_enabled",
            "Noise reduction",
            "Reduziert Hintergrundrauschen vor der Transkription.",
            config.get("noise_reduction_enabled", True),
        )
        + _switch(
            "audio_feedback_enabled",
            "Audio feedback",
            "Spielt Töne beim Starten und Stoppen der Aufnahme.",
            config.get("audio_feedback_enabled", True),
        )
    )

    transcription_rows = (
        _select(
            "transcription_backend",
            "Backend",
            "Wählt Dienst oder lokales Modell.",
            [
                ("deepgram", "Deepgram Nova-3"),
                ("elevenlabs", "ElevenLabs Scribe v2"),
                ("openai", "OpenAI Whisper"),
                ("faster_whisper", "faster-whisper"),
                ("streaming", "sherpa-onnx"),
            ],
            config.get("transcription_backend", "openai"),
        )
        + _field(
            "faster_whisper_model",
            "Local model",
            "Modellname für faster-whisper.",
            config.get("faster_whisper_model", "medium"),
        )
        + _switch(
            "postprocess_enabled",
            "Post-processing",
            "Bereinigt Leerzeichen, Satzzeichen und Großschreibung.",
            config.get("postprocess_enabled", True),
        )
    )

    flow_primary_rows = (
        _switch(
            "flow_mode_enabled",
            "Flow Mode",
            "Aktiviert die Wispr-Flow-artige Diktatpipeline.",
            config.get("flow_mode_enabled", False),
        )
        + _switch(
            "flow_context_awareness_enabled",
            "Context awareness",
            "Passt Format und Einfügen an die aktive App an.",
            config.get("flow_context_awareness_enabled", True),
        )
        + _switch(
            "flow_smart_formatting_enabled",
            "Smart formatting",
            "Formatiert natürliche Sprache zu Text, Listen und Zeilenumbrüchen.",
            config.get("flow_smart_formatting_enabled", True),
        )
        + _switch(
            "flow_backtrack_enabled",
            "Backtrack",
            "Erlaubt Korrekturen wie kürzer, länger oder umformulieren.",
            config.get("flow_backtrack_enabled", True),
        )
    )

    flow_controls_rows = (
        _select(
            "flow_default_profile",
            "Default profile",
            "Standardprofil, falls keine App-Regel greift.",
            [
                ("default", "Default"),
                ("chat", "Chat"),
                ("email", "Email"),
                ("notes", "Notes"),
                ("editor", "Editor"),
                ("terminal", "Terminal"),
            ],
            config.get("flow_default_profile", "default"),
        )
        + _field(
            "flow_preferred_languages",
            "Preferred languages",
            "Kommagetrennte Sprachliste für Flow.",
            preferred_languages_text,
        )
        + _field(
            "flow_max_recording_minutes",
            "Max recording",
            "Maximale Aufnahmezeit in Minuten.",
            config.get("flow_max_recording_minutes", 20),
            "number",
        )
    )

    privacy_rows = (
        _select(
            "flow_history_storage",
            "History storage",
            "Wie Flow-Verlauf gespeichert werden soll.",
            [
                ("normal", "Normal"),
                ("auto_delete", "Auto-delete after 24h"),
                ("never", "Never store"),
            ],
            config.get("flow_history_storage", "normal"),
        )
        + _switch(
            "flow_dictionary_enabled",
            "Dictionary",
            "Nutzt eigene Wortersetzungen wie WhisprBar.",
            config.get("flow_dictionary_enabled", True),
        )
        + _switch(
            "flow_snippets_enabled",
            "Snippets",
            "Erweitert gesprochene Kürzel zu längeren Textbausteinen.",
            config.get("flow_snippets_enabled", True),
        )
    )

    advanced_rows = (
        _switch(
            "recording_indicator_enabled",
            "Flow indicator",
            "Zeigt den modernen Aufnahmeindikator.",
            config.get("recording_indicator_enabled", True),
        )
        + _select(
            "recording_indicator_position",
            "Indicator position",
            "Position des Aufnahmeindikators.",
            [
                ("top-center", "Top center"),
                ("top-left", "Top left"),
                ("top-right", "Top right"),
                ("bottom-center", "Bottom center"),
                ("draggable", "Draggable"),
            ],
            config.get("recording_indicator_position", "top-center"),
        )
        + _switch(
            "chunking_enabled",
            "Chunking",
            "Teilt lange Aufnahmen für stabilere Verarbeitung.",
            config.get("chunking_enabled", True),
        )
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(APP_NAME)} Settings</title>
<style>
  :root {{
    color-scheme: dark;
    --window-min-width: 1080px;
    --bg: #0d1218;
    --panel: #121a23;
    --panel-2: #101821;
    --card: rgba(255,255,255,0.052);
    --card-strong: rgba(255,255,255,0.068);
    --border: rgba(255,255,255,0.105);
    --muted: #8f9dad;
    --text: #e8f0f7;
    --accent: #67d6ff;
    --accent-2: #7d8cff;
    --hairline: inset 0 0 0 1px rgba(255,255,255,0.075);
    --soft-shadow: 0 18px 60px rgba(0,0,0,0.24);
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    min-height: 100vh;
    background: var(--bg);
    color: var(--text);
    font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-size: 14px;
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
  }}
  button, input, select {{ font: inherit; }}
  .wb-frame {{
    min-width: var(--window-min-width);
    min-height: 100vh;
    background: var(--bg);
    overflow: hidden;
  }}
  .wb-windowbar {{
    height: 52px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 20px;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    background: var(--panel);
  }}
  .wb-title {{
    display: flex;
    align-items: center;
    gap: 10px;
    font-weight: 700;
  }}
  .wb-logo {{
    width: 30px;
    height: 30px;
    border-radius: 8px;
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    color: #061016;
    display: grid;
    place-items: center;
    font-size: 11px;
    font-weight: 800;
    box-shadow: 0 0 0 1px rgba(255,255,255,0.22) inset;
  }}
  .wb-actions {{ display: flex; gap: 8px; }}
  .wb-button {{
    height: 32px;
    border: 0;
    border-radius: 8px;
    padding: 0 14px;
    background: rgba(255,255,255,0.08);
    color: #c8d3de;
    box-shadow: var(--hairline);
    cursor: pointer;
  }}
  .wb-button.primary {{
    background: var(--accent);
    color: #071118;
    font-weight: 700;
    box-shadow: 0 0 0 1px rgba(255,255,255,0.30) inset, 0 8px 22px rgba(103,214,255,0.16);
  }}
  .wb-button:hover {{ background: rgba(255,255,255,0.115); }}
  .wb-button.primary:hover {{ background: #7adeff; }}
  .wb-shell {{
    display: grid;
    grid-template-columns: 218px minmax(0, 1fr);
    min-height: calc(100vh - 52px);
  }}
  .wb-sidebar {{
    padding: 18px 12px;
    background: var(--panel-2);
    border-right: 1px solid rgba(255,255,255,0.08);
  }}
  .wb-nav-label {{
    padding: 8px 10px 10px;
    color: #71808e;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }}
  .wb-nav {{ display: grid; gap: 4px; }}
  .wb-nav-item {{
    display: grid;
    grid-template-columns: 20px 1fr auto;
    align-items: center;
    gap: 10px;
    min-height: 40px;
    border: 0;
    border-radius: 9px;
    padding: 0 12px;
    color: #b5c0cc;
    background: transparent;
    text-align: left;
    cursor: pointer;
  }}
  .wb-nav-item:hover {{ background: rgba(255,255,255,0.055); }}
  .wb-nav-item.active {{
    background: linear-gradient(135deg, #223347, #1a2938);
    color: #f6fbff;
    box-shadow: var(--hairline);
  }}
  .wb-icon {{
    width: 10px;
    height: 10px;
    border-radius: 99px;
    background: #536170;
  }}
  .wb-nav-item.active .wb-icon {{ background: var(--accent); }}
  .wb-count {{ font-size: 10px; color: #8fa0af; }}
  .wb-main {{
    padding: 26px 30px 30px;
    background: #0d1218;
    overflow: auto;
  }}
  .wb-page {{ display: none; max-width: 1180px; }}
  .wb-page.active {{ display: block; }}
  .wb-page-head {{
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 16px;
    align-items: start;
    margin-bottom: 22px;
  }}
  .wb-page-head h2 {{ margin: 0 0 6px; font-size: 26px; letter-spacing: 0; }}
  .wb-page-head p {{ margin: 0; color: #9aa8b6; line-height: 1.45; }}
  .wb-status-pill {{
    height: 32px;
    display: flex;
    align-items: center;
    gap: 7px;
    border-radius: 999px;
    padding: 0 12px;
    background: rgba(103, 214, 255, 0.12);
    box-shadow: 0 0 0 1px rgba(103, 214, 255, 0.24) inset;
    color: #bdefff;
    font-size: 12px;
  }}
  .wb-dot {{
    width: 7px;
    height: 7px;
    border-radius: 99px;
    background: var(--accent);
  }}
  .wb-layout {{
    display: grid;
    grid-template-columns: minmax(0, 1.2fr) minmax(270px, 0.8fr);
    gap: 18px;
  }}
  .wb-stack {{ display: grid; gap: 16px; }}
  .wb-section {{
    border: 0;
    border-radius: 12px;
    background: var(--card);
    box-shadow: var(--hairline), var(--soft-shadow);
    overflow: hidden;
  }}
  .wb-hero {{
    background: linear-gradient(135deg, rgba(83,170,220,0.18), rgba(255,255,255,0.04));
    box-shadow: inset 0 0 0 1px rgba(103,214,255,0.22), var(--soft-shadow);
  }}
  .wb-section-head {{
    padding: 15px 16px;
    border-bottom: 1px solid rgba(255,255,255,0.07);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }}
  .wb-section-head h3 {{ margin: 0; font-size: 14px; }}
  .wb-section-head span {{ color: #8d9cac; font-size: 12px; }}
  .wb-row {{
    min-height: 54px;
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    gap: 18px;
    padding: 9px 16px;
    border-top: 1px solid rgba(255,255,255,0.055);
  }}
  .wb-row:hover {{ background: rgba(255,255,255,0.026); }}
  .wb-row:first-of-type {{ border-top: 0; }}
  .wb-row-label {{ display: grid; gap: 3px; min-width: 0; }}
  .wb-row-label b {{ font-size: 13px; font-weight: 650; color: #dce5ee; }}
  .wb-row-label span {{ font-size: 11px; color: #8998a7; line-height: 1.38; }}
  input, select {{
    height: 34px;
    min-width: 138px;
    border-radius: 8px;
    background: #18232e;
    border: 0;
    box-shadow: inset 0 0 0 1px rgba(255,255,255,0.105);
    color: #d5e0ea;
    padding: 0 11px;
    outline: none;
  }}
  input:focus, select:focus {{ box-shadow: inset 0 0 0 1px rgba(103,214,255,0.62), 0 0 0 3px rgba(103,214,255,0.10); }}
  .wb-switch-input {{
    appearance: none;
    width: 42px;
    height: 24px;
    min-width: 42px;
    padding: 0;
    border: 0;
    border-radius: 99px;
    background: #2c4052;
    position: relative;
  }}
  .wb-switch-input::after {{
    content: "";
    position: absolute;
    left: 2px;
    top: 2px;
    width: 20px;
    height: 20px;
    border-radius: 99px;
    background: #8fa0af;
    transition: left 120ms ease, background 120ms ease;
  }}
  .wb-switch-input:checked::after {{
    left: 20px;
    background: var(--accent);
  }}
  .wb-table {{ padding: 13px 16px 16px; display: grid; gap: 8px; }}
  .wb-table-head, .wb-table-row {{
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) 42px;
    gap: 8px;
  }}
  .wb-table-head {{
    color: #7f8d9b;
    font-size: 11px;
    padding: 0 4px 2px;
  }}
  .wb-table-row input {{ width: 100%; min-width: 0; }}
  .wb-table-row button {{
    border: 0;
    border-radius: 8px;
    background: rgba(255,255,255,0.08);
    color: #cbd7e3;
    cursor: pointer;
  }}
  .wb-note {{
    padding: 14px 16px;
    color: #91a1b1;
    font-size: 12px;
    line-height: 1.45;
  }}
  @media (max-width: 760px) {{
    .wb-shell {{ grid-template-columns: 1fr; }}
    .wb-sidebar {{ border-right: 0; border-bottom: 1px solid rgba(255,255,255,0.08); }}
    .wb-layout {{ grid-template-columns: 1fr; }}
    .wb-page-head {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>
<form class="wb-frame wb-polished">
  <header class="wb-windowbar">
    <div class="wb-title"><span class="wb-logo">WB</span><span>WhisprBar Settings</span></div>
    <div class="wb-actions">
      <button class="wb-button" type="button">Cancel</button>
      <button class="wb-button primary" type="button">Save Changes</button>
    </div>
  </header>
  <div class="wb-shell">
    <aside class="wb-sidebar">
      <div class="wb-nav-label">Settings</div>
      <nav class="wb-nav" aria-label="Settings pages">
        <button class="wb-nav-item active" type="button" data-page="general"><span class="wb-icon"></span><span>General</span><span class="wb-count">4</span></button>
        <button class="wb-nav-item" type="button" data-page="recording"><span class="wb-icon"></span><span>Recording</span><span class="wb-count">4</span></button>
        <button class="wb-nav-item" type="button" data-page="transcription"><span class="wb-icon"></span><span>Transcription</span><span class="wb-count">3</span></button>
        <button class="wb-nav-item" type="button" data-page="flow"><span class="wb-icon"></span><span>Flow</span><span class="wb-count">8</span></button>
        <button class="wb-nav-item" type="button" data-page="privacy"><span class="wb-icon"></span><span>Privacy</span><span class="wb-count">3</span></button>
        <button class="wb-nav-item" type="button" data-page="advanced"><span class="wb-icon"></span><span>Advanced</span><span class="wb-count">3</span></button>
      </nav>
    </aside>
    <main class="wb-main">
      <section class="wb-page active" data-page-id="general">
        <div class="wb-page-head">
          <div><h2>General</h2><p>Basisverhalten, Sprache und Einfügen bleiben kompakt erreichbar.</p></div>
          <span class="wb-status-pill"><span class="wb-dot"></span> Local preview</span>
        </div>
        <div class="wb-stack">{_section("App behavior", "Core", general_rows, hero=True)}</div>
      </section>

      <section class="wb-page" data-page-id="recording">
        <div class="wb-page-head">
          <div><h2>Recording</h2><p>Aufnahmequalität, VAD und akustisches Feedback.</p></div>
          <span class="wb-status-pill"><span class="wb-dot"></span> Audio</span>
        </div>
        <div class="wb-stack">{_section("Capture", "Input and cleanup", recording_rows, hero=True)}</div>
      </section>

      <section class="wb-page" data-page-id="transcription">
        <div class="wb-page-head">
          <div><h2>Transcription</h2><p>Backend, Modell und Nachbearbeitung.</p></div>
          <span class="wb-status-pill"><span class="wb-dot"></span> Engine</span>
        </div>
        <div class="wb-stack">{_section("Engine", "Backend", transcription_rows, hero=True)}</div>
      </section>

      <section class="wb-page" data-page-id="flow">
        <div class="wb-page-head">
          <div><h2>Flow</h2><p>Die wichtigsten Wispr-Flow-artigen Funktionen an einem Ort.</p></div>
          <span class="wb-status-pill"><span class="wb-dot"></span> Flow ready</span>
        </div>
        <div class="wb-layout">
          <div class="wb-stack">
            {_section("Flow Mode", "Behavior", flow_primary_rows, hero=True)}
            {_section("Profiles", "Context", flow_controls_rows)}
          </div>
          <div class="wb-stack">
            <section class="wb-section">
              <div class="wb-section-head"><h3>Dictionary</h3><span>Spoken -> written</span></div>
              <div class="wb-table">
                <div class="wb-table-head"><span>Recognized</span><span>Insert as</span><span></span></div>
                {dictionary_rows}
              </div>
            </section>
            <section class="wb-section">
              <div class="wb-section-head"><h3>Snippets</h3><span>Trigger -> text</span></div>
              <div class="wb-table">
                <div class="wb-table-head"><span>Trigger</span><span>Text</span><span></span></div>
                {snippet_rows}
              </div>
            </section>
          </div>
        </div>
      </section>

      <section class="wb-page" data-page-id="privacy">
        <div class="wb-page-head">
          <div><h2>Privacy</h2><p>Verlauf, lokale Flow-Dateien und Speicherung.</p></div>
          <span class="wb-status-pill"><span class="wb-dot"></span> Local files</span>
        </div>
        <div class="wb-stack">{_section("Storage", "History and local helpers", privacy_rows, hero=True)}</div>
      </section>

      <section class="wb-page" data-page-id="advanced">
        <div class="wb-page-head">
          <div><h2>Advanced</h2><p>Technische Einstellungen für Indikator, Overlay und lange Aufnahmen.</p></div>
          <span class="wb-status-pill"><span class="wb-dot"></span> Expert</span>
        </div>
        <div class="wb-stack">
          {_section("Runtime", "Technical", advanced_rows, hero=True)}
          <section class="wb-section"><div class="wb-note">Dieser WebKit-Prototyp schreibt noch keine Einstellungen. Er dient zum realen visuellen Vergleich im nativen Fenster, bevor wir die Speichern-Logik migrieren.</div></section>
        </div>
      </section>
    </main>
  </div>
</form>
<script>
  const navButtons = [...document.querySelectorAll('.wb-nav-item')];
  const pages = [...document.querySelectorAll('.wb-page')];
  for (const button of navButtons) {{
    button.addEventListener('click', () => {{
      const page = button.dataset.page;
      navButtons.forEach(item => item.classList.toggle('active', item === button));
      pages.forEach(item => item.classList.toggle('active', item.dataset.pageId === page));
    }});
  }}
</script>
</body>
</html>"""


def open_settings_webview_window(
    config: Mapping[str, object],
    state: Optional[Mapping[str, object]] = None,
    on_save: Optional[object] = None,
) -> bool:
    """Open the experimental WebKit settings preview window."""

    del state, on_save

    try:
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("WebKit2", "4.1")
        from gi.repository import Gtk, WebKit2
    except Exception as exc:
        notify("WebKit settings preview is unavailable.")
        print(f"[WARN] WebKit settings preview unavailable: {exc}")
        return False

    window = Gtk.Window(title=f"{APP_NAME} Settings Preview")
    window.set_position(Gtk.WindowPosition.CENTER)
    window.set_default_size(1120, 760)
    window.set_resizable(True)

    webview = WebKit2.WebView()
    window.add(webview)
    html = generate_settings_html(
        config,
        dictionary_entries=load_dictionary(),
        snippets=load_snippets(),
    )
    webview.load_html(html, "file:///")
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    return True


def main() -> None:
    """Run the experimental settings preview as a standalone window."""

    from whisprbar.config import load_config

    config = load_config()
    if open_settings_webview_window(config, {}):
        import gi

        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk

        Gtk.main()


if __name__ == "__main__":
    main()
