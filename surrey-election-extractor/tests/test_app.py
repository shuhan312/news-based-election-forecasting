"""Page-level tests for the Streamlit election extractor interface."""

from pathlib import Path

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).parents[1] / "app.py"


def _load_app() -> AppTest:
    """Run one local page render without starting a server or using SerpAPI."""

    return AppTest.from_file(str(APP_PATH)).run(timeout=10)


def test_page_loads_with_the_supervisor_required_controls() -> None:
    """Check the title, two inputs, search option and extraction button."""

    app = _load_app()

    # This is a presentation-contract test: renaming or removing a control in
    # the future will fail here before it silently diverges from the prompt.
    assert not app.exception
    assert app.title[0].value == "Surrey Election Results Extractor"
    assert app.text_input[0].label == "Surrey election results URL"
    assert app.text_input[1].label == "Indexed results API key"
    # Streamlit's testing wrapper labels every widget object as ``text_input``;
    # the underlying widget protocol records whether its browser rendering is
    # masked. PASSWORD is enum value 1 in that protocol.
    assert app.text_input[1].proto.type == 1
    assert app.checkbox[0].label == "Run targeted searches for missing information"
    assert app.checkbox[0].value is True
    assert app.button[0].label == "Extract election results"


def test_extraction_button_is_disabled_until_both_inputs_are_present() -> None:
    """Prevent an avoidable extraction request with missing user input."""

    app = _load_app()
    assert app.button[0].disabled is True

    # Entering only the URL is insufficient because indexed discovery also
    # requires the temporary provider credential.
    app.text_input[0].set_value(
        "https://mycouncil.surreycc.gov.uk/"
        "mgElectionElectionAreaResults.aspx?EID=16"
    ).run(timeout=10)
    assert app.button[0].disabled is True

    app.text_input[1].set_value("local-test-key").run(timeout=10)
    assert app.button[0].disabled is False


def test_invalid_url_shows_safe_error_and_clears_the_password() -> None:
    """Retain helpful validation feedback after removing the temporary key."""

    app = _load_app()
    app.text_input[0].set_value("https://example.org/not-a-surrey-election")
    app.text_input[1].set_value("temporary-test-credential")
    app.run(timeout=10)
    app.button[0].click().run(timeout=10)

    # This one request checks three linked safety rules: friendly validation,
    # credential removal, and no misleading download after failure.
    assert not app.exception
    assert len(app.error) == 1
    assert "valid Surrey election" in app.error[0].value
    assert "temporary-test-credential" not in app.error[0].value
    assert app.text_input[1].value == ""
    assert not app.download_button
