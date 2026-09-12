# DiscordBotHelper

Run and restart a Python bot from the current directory.

## Install

```powershell
uv tool install .
```

This installs the `DiscordBotHelper` command.

## Usage

```powershell
DiscordBotHelper .\Do_Not_Disturb.py
DiscordBotHelper --force .\Do_Not_Disturb.py
```

The bot file is resolved from the current directory, and `restart.txt` and
`startup.txt` are also read and created there.

Without `--force`, pressing Enter creates `restart.txt` and waits for the bot
to shut itself down. With `--force`, pressing Enter sends a shutdown signal
directly to the bot process and starts it again after it exits. On Windows,
the signal is sent to the child process group with `CTRL_BREAK_EVENT`, which
is the reliable programmatic equivalent of Ctrl+C.
