# /// script
# requires-python = ">=3.10"
# dependencies = ["click"]
# ///
"""Bootstrap for the arena CLI, run as `uv run --script` by the shell shim."""

import cli

cli.main(prog_name="arena")
