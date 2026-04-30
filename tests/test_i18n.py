from whisprbar.i18n import get_language, t


def test_get_language_accepts_supported_values_only():
    assert get_language({"language": "de"}) == "de"
    assert get_language({"language": "en"}) == "en"
    assert get_language({"language": "fr"}) == "en"
    assert get_language({}) == "en"


def test_t_returns_translated_text_and_falls_back_to_english():
    assert t("settings.title", {"language": "de"}) == "WhisprBar Einstellungen"
    assert t("settings.title", {"language": "en"}) == "WhisprBar Settings"
    assert t("missing.key", {"language": "de"}) == "missing.key"

