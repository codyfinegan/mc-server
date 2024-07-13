import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import click

from .configuration import Config


def factory(world: str, config: Config):
    cls = globals()[f"MCA{world.title()}"]
    return cls(config)


class MCAManager:
    def __init__(self, config: Config) -> None:
        self.config = config

    def title(self):
        raise NotImplementedError("Must implement title()")

    def folder(self):
        return str(self._world())

    def _query(self) -> str:
        raise NotImplementedError("Must implement _query()")

    def _world(self) -> Path:
        raise NotImplementedError("Must implement _world()")

    def _region(self) -> Path:
        return self._world().joinpath("")

    def _fname(self) -> str:
        return self.title().replace(" ", "-").lower()

    def _output(self) -> Path:
        return Path("chunks-{}.csv".format(self._fname()))

    def _dir(self) -> Path:
        return Path("chunks-{}".format(self._fname()))

    def _run(self, debug: bool, mode: str, *args):
        world = str(self._world().absolute())
        base = str(Path(self.config.tree_str("mca", "bin")))

        command = [*base.split(" "), "--world", world, "--mode", mode, *args]

        if debug:
            # click.echo(f"Command: {' '.join(command)}")
            print(command)
            return

        return subprocess.call(
            command,
            stderr=subprocess.STDOUT,
        )

    def select(self, preview: bool, debug: bool):
        query = self._query().replace('"', '"')
        if preview:
            click.echo(query)
            return

        # Output, where we write things
        output = str(self._output().absolute())

        code = self._run(debug, "select", "--query", query, "--output", output)

        if code > 0:
            click.echo("There was an error processing the command")
            return

        click.echo("Output has been written to {}".format(output))

    def backup(self, debug: bool):
        #  Output Folder
        dir = self._dir()
        if dir.exists():
            shutil.rmtree(dir)

        dir.mkdir(parents=False)
        if not dir.exists():
            raise click.UsageError(
                "Unable to write to temporary directory {}".format(dir.absolute()),
            )

        output = self._output()
        if not output.exists():
            raise click.UsageError(
                "Chunks CSV file wasn't there, run the select command first.",
            )

        world_dir = Path(dir.joinpath("world"))

        self._run(
            debug,
            "export",
            "--selection",
            str(output.absolute()),
            "--output",
            str(dir.absolute()),
            "--output-world",
            str(world_dir.absolute()),
        )

        cfg = self.config.get_dict("mca")

        # Compress the chunks
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        compressed_name = cfg["name"] % f"{self._fname()}_{timestamp}"

        if not cfg["compress"]:
            compress_command = [
                "tar",
                "-c",
                "-f",
                str(compressed_name),
                "-C",
                str(dir.absolute()),
                ".",
            ]
        else:
            compress_command = [
                "tar",
                "-c",
                "-I",
                f"{cfg['compress']}",
                "-f",
                str(compressed_name),
                "-C",
                str(dir.absolute()),
                ".",
            ]

        if debug:
            print(compress_command)
            return

        click.echo("Compressing files")
        subprocess.call(
            compress_command,
            stderr=subprocess.STDOUT,
        )

        if Path(compressed_name).exists():
            click.echo("Backed up to {}".format(compressed_name))
        else:
            click.echo("Failed to compress")

        if dir.exists():
            shutil.rmtree(dir)


class MCAOverworld(MCAManager):
    def title(self):
        return "The Overworld"

    def _query(self) -> str:
        return (
            "!(!"
            "(xPos < -64 OR xPos > 31 OR zPos < -64 OR zPos > 31)"
            " OR "
            'InhabitedTime > "5 minutes"'
            " OR "
            'Palette contains "minecraft:lapis_block")'
        )

    def _world(self) -> Path:
        return Path(self.config.get_str("game_folder")).joinpath(
            Path(self.config.get_str("world")),
        )


class MCANether(MCAOverworld):
    def title(self):
        return "The Nether"

    def _world(self) -> Path:
        return super()._world().joinpath("DIM-1")


class MCAEnd(MCAOverworld):
    def title(self):
        return "The End"

    def _query(self) -> str:
        return (
            "!(!(xPos < -32 OR xPos > 31 OR zPos < -32 OR zPos > 31)"
            ' OR Palette contains "minecraft:lapis_block"'
            ' OR Palette contains "minecraft:end_gateway"'
            ' OR Palette contains "minecraft:cobblestone"'
            ' OR Palette contains "minecraft:stone"'
            ' OR Palette contains "minecraft:obsidian"'
            ' OR Palette contains "minecraft:redstone_wire"'
            ' OR Palette contains "minecraft:water"'
            ")"
        )

    def _world(self) -> Path:
        return super()._world().joinpath("DIM1")
