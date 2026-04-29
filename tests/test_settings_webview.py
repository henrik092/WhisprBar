from whisprbar.flow.models import DictionaryEntry, Snippet
from whisprbar.ui.settings_webview import generate_settings_html


def test_generate_settings_html_contains_selected_settings_shell():
    html = generate_settings_html(
        {
            "theme_preference": "dark",
            "language": "de",
            "transcription_backend": "deepgram",
            "flow_mode_enabled": True,
            "flow_dictionary_enabled": True,
            "flow_snippets_enabled": False,
        },
        dictionary_entries=[],
        snippets=[],
    )

    assert "WhisprBar Settings" in html
    assert "data-page=\"general\"" in html
    assert "data-page=\"flow\"" in html
    assert "Flow Mode" in html
    assert "Deepgram Nova-3" in html
    assert "checked" in html


def test_generate_settings_html_escapes_dictionary_and_snippet_values():
    html = generate_settings_html(
        {"flow_mode_enabled": True},
        dictionary_entries=[
            DictionaryEntry(spoken="<Vispaba>", written="WhisprBar & Flow"),
        ],
        snippets=[
            Snippet(trigger="sig <x>", text="Best & regards"),
        ],
    )

    assert "&lt;Vispaba&gt;" in html
    assert "WhisprBar &amp; Flow" in html
    assert "sig &lt;x&gt;" in html
    assert "Best &amp; regards" in html
    assert "<Vispaba>" not in html


def test_generate_settings_html_uses_monitor_polished_density_tokens():
    html = generate_settings_html(
        {"flow_mode_enabled": True},
        dictionary_entries=[],
        snippets=[],
    )

    assert 'class="wb-frame wb-polished"' in html
    assert "--window-min-width: 1080px" in html
    assert "font-size: 14px" in html
    assert "grid-template-columns: 218px minmax(0, 1fr)" in html
