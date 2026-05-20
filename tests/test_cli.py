from skillup.cli import app
from skillup.settings import settings
from typer.testing import CliRunner

runner = CliRunner()

def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "add" in result.stdout
    assert "remove" in result.stdout
    assert "update" in result.stdout
    assert "sync" in result.stdout


def test_system_certs_flag_sets_setting():
    settings.use_system_certs = False
    result = runner.invoke(app, ["--system-certs", "sync"])
    assert result.exit_code == 0
    assert settings.use_system_certs is True
    settings.use_system_certs = False
