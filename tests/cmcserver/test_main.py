import subprocess
from pathlib import Path

import click
from click.testing import CliRunner

from cmcserver.configuration import Config
from cmcserver.main import cli


def patch_call(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "call",
        lambda command, *args, **kwargs: print(f"Command issued: {command}"),
    )


def patch_edit(monkeypatch):
    monkeypatch.setattr(
        click,
        "edit",
        lambda filename, *args, **kwargs: print(f"Edit issued: {filename}"),
    )


def test_config(monkeypatch):
    runner = CliRunner()
    with runner.isolated_filesystem() as r:
        config_file = Path(r).joinpath("cmcserver.toml")
        output = runner.invoke(cli, ["config", "--path", "--config", str(config_file)])
        assert "cmcserver.toml" in output.output

        output = runner.invoke(
            cli,
            ["config", "--default", "--config", str(config_file)],
        )
        assert "# Configuration for cmcserver command" in output.output
        assert "startup_script" in output.output

        # Assert we get prompted for non-existent
        output = runner.invoke(cli, ["config", "--config", str(config_file)])
        assert "Do you want to create it with default values" in output.output
        assert "No config file was created" in output.output

        output = runner.invoke(cli, ["config", "--config", str(config_file)], input="y")
        assert "# Configuration for cmcserver command" in output.output
        assert config_file.exists()

        patch_edit(monkeypatch)
        output = runner.invoke(cli, ["config", "--edit", "--config", str(config_file)])
        assert "Edit issued" in output.output

        output = runner.invoke(cli, ["config", "--config", str(config_file)])
        assert "backups.aws.bucket" in output.output

        output = runner.invoke(cli, ["config", "--raw", "--config", str(config_file)])
        assert "# Configuration for cmcserver command" in output.output

        output = runner.invoke(
            cli,
            ["config", "--delete", "--config", str(config_file)],
        )
        assert "Deleted the config file" in output.output
        assert not config_file.exists()


def test_download_mods(monkeypatch):
    runner = CliRunner()
    with runner.isolated_filesystem() as r:
        config = Config(dict(), False)

        def set_config(key, value):
            config.data[key] = value
            monkeypatch.setattr(Config, "load", lambda x, y: config)

        def invoke(debug=False):
            output = runner.invoke(cli, ["mods"])
            return output.output

        # Assert validation on failure
        set_config("mod_script", "")
        assert "Must define a mod_script" in invoke()

        # Make a dummy download file
        mod_file = Path(r).joinpath("mod_file.sh")
        set_config("mod_script", str(mod_file))
        assert f"{str(mod_file)} does not exist" in invoke()

        # Make it actually real
        with open(mod_file, "w") as f:
            f.write('echo "mod_script"')

        # Debug
        config.debug = True
        set_config("mod_script", str(mod_file))
        assert "Command: " in invoke()

        config.debug = False
        set_config("mod_script", str(mod_file))
        patch_call(monkeypatch)
        output = invoke()
        assert f"Command issued: ['{str(mod_file)}']" in output
        assert "Complete" in output
