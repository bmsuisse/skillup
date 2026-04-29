from bms_skills.cli import app
from typer.testing import CliRunner

runner = CliRunner()

def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "add" in result.stdout
    assert "remove" in result.stdout
    assert "update" in result.stdout
