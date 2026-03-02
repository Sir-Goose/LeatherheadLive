from app.tools import build_nr_timetable_index as tool


def test_main_returns_zero_for_success(monkeypatch, capsys):
    monkeypatch.setattr(
        tool,
        "build_index",
        lambda: {"status": "ok", "index_path": "/tmp/example.sqlite3"},
    )

    code = tool.main()
    output = capsys.readouterr().out

    assert code == 0
    assert '"status": "ok"' in output


def test_main_returns_one_for_failure(monkeypatch, capsys):
    monkeypatch.setattr(
        tool,
        "build_index",
        lambda: {"status": "missing_zip", "zip_path": "/missing.zip"},
    )

    code = tool.main()
    output = capsys.readouterr().out

    assert code == 1
    assert '"status": "missing_zip"' in output
