from click.testing import CliRunner

from cmcserver.main import cli


def test_cli():
    runner = CliRunner()
    with runner.isolated_filesystem():
        output = runner.invoke(cli, ["config", "--path"])
        assert "cmcserver.toml" in output.output
