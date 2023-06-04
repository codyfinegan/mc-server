# mc-server
A python utility to manage my Minecraft server

[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/codyfinegan/mc-server/main.svg)](https://results.pre-commit.ci/latest/github/codyfinegan/mc-server/main) ![python tests](https://img.shields.io/github/actions/workflow/status/codyfinegan/mc-server/python-test.yml) ![license](https://img.shields.io/github/license/codyfinegan/mc-server) ![language](https://img.shields.io/github/languages/top/codyfinegan/mc-server)

## Installation
Requires `zstd` for backup compression. Try `apt install zstd`.
Clone the project, setup a virtual env and install `pip install .`

### Configuration
Generate the default config file using `cmcserver config` in the regular place. Run `cmcserver config --help` to see all of the available options.

Below is an example of the configuration file with their default values.

[//]: # (config-start)
```
# Configuration for cmcserver command

startup_script = "/path/to/startup_script.sh" # Full path to the startup script.
game_folder = "/path/to/game" # The path to the minecraft base folder that holds the world_name
world = "world" # Name of the minecraft game folder
boot_pause = 25 # How long to wait for the server to start before continuing. Increase this if needed.
mod_script = "/path/to/mod_downloads.sh" # Full path to the script used to download mods.

[server]
# Options related to server access, check your server.properties file.
# If running on the same server, make sure ports are blocked exernally
# so rcon and query cannot be accessed externally.
host = "127.0.0.1"
rcon_password = "" # Password set in server.properties. Make it good.
rcon_port = 25575
query_port = 25565

[backups]
# Backup configuration.
folder = "/path/to/backups" # Base path to the backups folder
full = "full"
incremental = "incremental"
compress = "/usr/bin/zstd -19 -T2" # Command to apply compression to the backups
name = "%s.tar.zst" # Syntax of the backup filename. If compression changes, change the extension here.

[backups.aws]
bucket = "" # Bucket to store full backups in.
subfolder = "" # Path inside the bucket to store backups in.

[backups.git]
push = false
```
[//]: # (config-end)

### Commands
Run `cmcserver` to see the list of available commands.

[//]: # (command-start)
```
Usage: cmcserver [OPTIONS] COMMAND [ARGS]...

  Utility commands related to running a Minecraft server.

Options:
  --debug / --no-debug
  -C, --config PATH
  --help                Show this message and exit.

backup  Backup and restore the game using both remote and local options
config  Edit the configuration file, or generate it if it does not exist.
mods    Run the download mods script if it is defined
readme  Update the readme with the config & commands
server  See commands relating to the server

server:
  restart  Restart the server
  start    Boot the server.
  status   See the status of the server
  stop     Stop the server

backup:
  aws     Backup and restore the game using AWS as a remote storage option
  create  Create either a full or incremental backup
  git     Upload incremental changes to git
  prune   Prune the backups in the local system

backup aws:
  prune  Delete excess backup files from a configured AWS S3 bucket
  sync   Upload and download full backup files to a configured AWS S3 bucket
```
[//]: # (command-end)

## Development
Project uses pre-commit. Install using `pre-commit install` and then confirm the webhook passes.
