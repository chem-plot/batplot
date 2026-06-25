from types import SimpleNamespace

from batplot.plot_modes.common.files import confirm_previous_path


def test_confirm_previous_path_accepts_existing_path(tmp_path):
    target = tmp_path / "plot.svg"
    target.write_text("svg", encoding="utf-8")
    owner = SimpleNamespace(last_path=str(target))
    prompts = []

    def _safe_input(prompt: str) -> str:
        prompts.append(prompt)
        return "y"

    result = confirm_previous_path(
        owner,
        "last_path",
        safe_input=_safe_input,
        missing_message="missing",
        missing_file_message="missing file {path}",
        confirm_prompt="Overwrite '{basename}'? ",
    )

    assert result == str(target)
    assert prompts == ["Overwrite 'plot.svg'? "]


def test_confirm_previous_path_rejects_declined_overwrite(tmp_path, capsys):
    target = tmp_path / "session.pkl"
    target.write_text("pickle", encoding="utf-8")
    owner = SimpleNamespace(last_path=str(target))

    result = confirm_previous_path(
        owner,
        "last_path",
        safe_input=lambda prompt: "n",
        missing_message="missing",
        missing_file_message="missing file {path}",
        confirm_prompt="Overwrite '{basename}'? ",
    )

    assert result is None
    assert "Canceled." in capsys.readouterr().out


def test_confirm_previous_path_reports_missing_file(capsys):
    owner = SimpleNamespace(last_path="/does/not/exist.bps")

    result = confirm_previous_path(
        owner,
        "last_path",
        safe_input=lambda prompt: "y",
        missing_message="missing",
        missing_file_message="missing file {path}",
        confirm_prompt="Overwrite '{basename}'? ",
    )

    assert result is None
    assert "missing file /does/not/exist.bps" in capsys.readouterr().out
