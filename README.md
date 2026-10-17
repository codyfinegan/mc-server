# mc-server
A python utility to manage my Minecraft server

[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/codyfinegan/mc-server/main.svg)](https://results.pre-commit.ci/latest/github/codyfinegan/mc-server/main) ![python tests](https://img.shields.io/github/actions/workflow/status/codyfinegan/mc-server/python-test.yml) ![license](https://img.shields.io/github/license/codyfinegan/mc-server) ![language](https://img.shields.io/github/languages/top/codyfinegan/mc-server) | [![codecov](https://codecov.io/gh/codyfinegan/mc-server/branch/main/graph/badge.svg?token=H0Q8D38QJP)](https://codecov.io/gh/codyfinegan/mc-server)

## Installation
Install with [uv](https://docs.astral.sh/uv/): clone the project and run `uv tool install .` to put `mctl` on your PATH.

## Development
Run `uv sync` to create the virtualenv with dev dependencies, then `uv run pytest` to run the tests.
Linting and formatting use ruff (`uv run ruff check .` / `uv run ruff format .`).

Project uses pre-commit. Install using `uv run pre-commit install` and then confirm the webhook passes.

Commit messages must follow [Conventional Commits](https://www.conventionalcommits.org/) (e.g. `feat: add backup pruning`, `fix(mca): handle empty region`).
The pre-commit `commit-msg` hook enforces this locally, and CI checks every commit in a pull request plus the PR title.
Use `uv run cz commit` for an interactive prompt.

Releases are automated with [release-please](https://github.com/googleapis/release-please): merging to `main` updates a release PR with the next version and changelog, and merging that PR tags the release. The package version comes from that tag via setuptools_scm.
