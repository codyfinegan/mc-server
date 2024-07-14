import subprocess

from cmcserver.configuration import Config
from cmcserver.mca import MCAEnd, MCAManager, MCAOverworld, MCAOverworldPurge, factory

config = Config(dict(), False)


def patch_call(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "call",
        lambda command, *args, **kwargs: print(f"Command issued: {' '.join(command)}"),
    )


def test_query(monkeypatch, capsys):
    payloads = [
        ("overworld", MCAOverworld, 'Palette contains "minecraft:redstone_wire"'),
        ("end", MCAEnd, 'Palette contains "minecraft:end_gateway"'),
        ("overworld-purge", MCAOverworldPurge, "xPos"),
    ]

    for key, cls, query in payloads:
        obj: MCAManager
        obj = factory(key, config)
        assert isinstance(obj, cls)

        # Call the query method
        assert query in obj._query()

        # Test the preview
        obj.select(preview=True, debug=False)
        output = capsys.readouterr()
        assert query in output.out

        # Test the debug
        obj.select(preview=True, debug=True)
        output = capsys.readouterr()
        assert query in output.out

        # Test the regular call
        patch_call(monkeypatch)
        obj.select(False, False)
        output = capsys.readouterr()
        assert query in output.out
        assert "--world" in output.out
        assert "Command issued: " in output.out
        assert "--mode select" in output.out
        assert "--query" in output.out
        assert "Output has been written" in output.out
