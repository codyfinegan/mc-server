import subprocess
from pathlib import Path

import click
from click.testing import CliRunner

from cmcserver.configuration import Config
from cmcserver.main import cli
from cmcserver.mca import MCAManager


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
        output = runner.invoke(cli, ["config", "--config", str(config_file)])
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
        config_file = Path(r).joinpath("cmcserver.toml")

        def set_config(key, value):
            config.data[key] = value
            monkeypatch.setattr(Config, "load", lambda x, y: config)

        def invoke(debug=False):
            output = runner.invoke(
                cli,
                ["--config", str(config_file), "server", "mods"],
            )
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


def test_generate_readme(monkeypatch):
    runner = CliRunner()
    with runner.isolated_filesystem() as r:
        readme = Path(r).joinpath("readme.md")
        config_file = Path(r).joinpath("cmcserver.toml")
        default_readme = [
            "GAP0",
            "[//]: # (config-start)",
            "CONFIG_HERE",
            "[//]: # (config-end)",
            "GAP1",
            "[//]: # (command-start)",
            "COMMANDS_HERE",
            "[//]: # (command-end)",
            "GAP2",
        ]
        with open(readme, "w") as f:
            f.write("\n".join(default_readme))

        with open(readme) as f:
            content = f.read()
        assert "GAP0" in content
        assert "GAP1" in content
        assert "GAP2" in content
        assert "CONFIG_HERE" in content
        assert "COMMANDS_HERE" in content

        output = runner.invoke(
            cli,
            ["--config", str(config_file), "readme", str(readme)],
        )
        assert "Readme has been updated" in output.output

        with open(readme) as f:
            content = f.read()
        assert "GAP0" in content
        assert "GAP1" in content
        assert "GAP2" in content
        assert "CONFIG_HERE" not in content
        assert "COMMANDS_HERE" not in content


def test_helps():
    runner = CliRunner()
    with runner.isolated_filesystem() as r:
        config_file_raw = Path(r).joinpath("cmcserver.toml")
        config_file_raw.write_text("")
        config_file = str(config_file_raw)

        # Base help
        output = runner.invoke(cli, ["--help"])
        assert "Usage: " in output.output
        assert (
            "Utility commands related to running a Minecraft server." in output.output
        )
        assert "server:" in output.output
        assert "backup:" in output.output

        output = runner.invoke(cli)
        assert "Usage: " in output.output
        assert (
            "Utility commands related to running a Minecraft server." in output.output
        )
        assert "server:" in output.output
        assert "backup:" in output.output

        # Backup help
        output = runner.invoke(cli, ["--config", config_file, "backup"])
        assert "Usage: " in output.output
        assert "aws:" in output.output

        # Server help
        output = runner.invoke(cli, ["--config", config_file, "server"])
        assert "Usage: " in output.output
        assert "Restart the server" in output.output

        # MCA help
        output = runner.invoke(cli, ["--config", config_file, "mca"])
        assert "Usage: " in output.output
        assert "chunk management" in output.output


def test_mca_select(monkeypatch):
    runner = CliRunner()
    with runner.isolated_filesystem() as r:
        config_file_raw = Path(r).joinpath("cmcserver.toml")
        config_file_raw.write_text("")
        config_file = str(config_file_raw)

        monkeypatch.setattr(
            MCAManager,
            "select",
            lambda self, preview, debug: print(
                f"Select called with preview: {str(preview)}, debug: {str(debug)}",
            ),
        )

        output = runner.invoke(cli, ["--config", config_file, "mca", "select"])
        assert "Select called with preview: False, debug: False" in output.output

        output = runner.invoke(
            cli,
            ["--config", config_file, "mca", "select", "--preview"],
        )
        assert "Select called with preview: True, debug: False" in output.output

        output = runner.invoke(
            cli,
            ["--config", config_file, "mca", "select", "--debug"],
        )
        assert "Select called with preview: False, debug: True" in output.output

        output = runner.invoke(
            cli,
            ["--config", config_file, "mca", "select", "--debug", "--preview"],
        )
        assert "Select called with preview: True, debug: True" in output.output


def test_mca_backup(monkeypatch):
    runner = CliRunner()
    with runner.isolated_filesystem() as r:
        config_file_raw = Path(r).joinpath("cmcserver.toml")
        config_file_raw.write_text("")
        config_file = str(config_file_raw)

        monkeypatch.setattr(
            MCAManager,
            "backup",
            lambda self, debug: print(f"Backup called with debug: {str(debug)}"),
        )

        output = runner.invoke(cli, ["--config", config_file, "mca", "backup"])
        assert "Backup called with debug: False" in output.output

        output = runner.invoke(
            cli,
            ["--config", config_file, "mca", "backup", "--debug"],
        )
        assert "Backup called with debug: True" in output.output


def test_mca_delete(monkeypatch):
    runner = CliRunner()
    with runner.isolated_filesystem() as r:
        config_file_raw = Path(r).joinpath("cmcserver.toml")
        config_file_raw.write_text("")
        config_file = str(config_file_raw)

        monkeypatch.setattr(
            MCAManager,
            "delete",
            lambda self, debug: print(f"Delete called with debug: {str(debug)}"),
        )

        output = runner.invoke(cli, ["--config", config_file, "mca", "delete"])
        assert "Delete called with debug: False" in output.output

        output = runner.invoke(
            cli,
            ["--config", config_file, "mca", "delete", "--debug"],
        )
        assert "Delete called with debug: True" in output.output
