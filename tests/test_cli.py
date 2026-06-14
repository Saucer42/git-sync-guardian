import os

import pytest

from gsg import __version__
from gsg.cli import _parse_duration, main


def test_version(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_recover_help(capsys):
    rc = main(["recover-help"])
    assert rc == 0
    assert "recycle bin" in capsys.readouterr().out.lower()


def test_install_alias(capsys):
    rc = main(["install-alias", "--shell", "bash"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "gsg guard" in out


def test_parse_duration():
    assert _parse_duration("24h") == 86400
    assert _parse_duration("7d") == 7 * 86400
    assert _parse_duration("30m") == 1800
    with pytest.raises(ValueError):
        _parse_duration("nonsense")


def test_snapshot_command(tmp_repo, monkeypatch, capsys):
    (tmp_repo / "u.txt").write_text("untracked\n")
    monkeypatch.chdir(tmp_repo)
    rc = main(["snapshot"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Snapshot:" in out


def test_prune_floor_and_dry_run(tmp_path, monkeypatch, capsys):
    import tempfile

    fake_tmp = tmp_path / "tmp"
    fake_tmp.mkdir()
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(fake_tmp))
    old = fake_tmp / "gsg-20000101-000000"
    old.mkdir()
    os.utime(old, (0, 0))  # epoch -> very old
    rc = main(["prune", "--older-than", "1h", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "would delete" in out
    assert old.exists()  # dry-run did not delete
