import argparse
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from threading import Event


def resolve_python_interpreter(working_directory: Path) -> Path:
    environment_roots = [
        working_directory / ".venv",
        working_directory / "venv",
    ]
    active_environment = os.environ.get("VIRTUAL_ENV")
    if active_environment:
        environment_roots.append(Path(active_environment))

    executable_name = "python.exe" if os.name == "nt" else "python"
    for environment_root in environment_roots:
        interpreter = environment_root / ("Scripts" if os.name == "nt" else "bin") / executable_name
        if interpreter.is_file():
            return interpreter

    return Path(sys.executable)


def stream_output(pipe: object) -> None:
    for line in iter(pipe.readline, ""):
        if line:
            print(line.rstrip())
    pipe.close()


def start_bot(bot_file: Path, working_directory: Path) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    python_interpreter = resolve_python_interpreter(working_directory)

    creation_flags = 0
    if os.name == "nt":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP

    process = subprocess.Popen(
        [str(python_interpreter), "-u", str(bot_file)],
        cwd=working_directory,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        env=env,
        creationflags=creation_flags,
    )

    if process.stdout is not None:
        threading.Thread(
            target=stream_output,
            args=(process.stdout,),
            daemon=True,
        ).start()
    return process


def send_shutdown_signal(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return

    if os.name == "nt":
        process.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        process.send_signal(signal.SIGINT)


def stop_bot(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return

    try:
        send_shutdown_signal(process)
        process.wait(timeout=10)
    except Exception:
        try:
            process.kill()
            process.wait()
        except Exception:
            pass


def create_empty_file(path: Path) -> None:
    path.touch()


def remove_file_if_exists(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="DiscordBotHelper",
        description="Run and restart a Python bot script.",
    )
    parser.add_argument(
        "file",
        type=Path,
        help="Python bot file, resolved relative to the current directory",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Signal the bot directly instead of creating restart.txt",
    )
    args = parser.parse_args(argv)
    args.file = args.file.resolve()
    if not args.file.is_file():
        parser.error(f"bot file does not exist: {args.file}")
    return args


def watch_for_enter(restart_event: Event, shutdown_event: Event) -> None:
    while not shutdown_event.is_set():
        try:
            input()
        except EOFError:
            time.sleep(1)
            continue
        restart_event.set()


def run(bot_file: Path, force: bool = False) -> None:
    working_directory = Path.cwd()
    python_interpreter = resolve_python_interpreter(working_directory)
    restart_file = working_directory / "restart.txt"
    startup_file = working_directory / "startup.txt"
    restart_event = Event()
    shutdown_event = Event()
    bot_process = start_bot(bot_file, working_directory)
    shutdown_requested = False
    printed_bot_exit = False
    printed_waiting = False

    if force:
        print("Bot running. Press Enter to signal the bot and restart it.")
    else:
        print("Bot running. Press Enter or create restart.txt to request shutdown.")
    print(f"Using Python interpreter: {python_interpreter}")
    threading.Thread(
        target=watch_for_enter,
        args=(restart_event, shutdown_event),
        daemon=True,
    ).start()

    try:
        while True:
            while True:
                if restart_event.is_set():
                    restart_event.clear()
                    shutdown_requested = True
                    if force:
                        send_shutdown_signal(bot_process)
                        print("Restart signal received. Signaled bot directly.")
                    else:
                        create_empty_file(restart_file)
                        print("Restart signal received. Created restart.txt.")
                    time.sleep(1)
                    continue

                if startup_file.exists():
                    if bot_process.poll() is None:
                        if shutdown_requested and not printed_waiting:
                            print(
                                "startup file detected after restart; bot is still "
                                "running, waiting for bot to shutdown"
                            )
                            printed_waiting = True
                    else:
                        print("startup.txt found. Bot is not running, starting bot...")
                        time.sleep(5)
                        bot_process = start_bot(bot_file, working_directory)
                        shutdown_requested = False
                        printed_bot_exit = False
                        printed_waiting = False

                    if not shutdown_requested:
                        remove_file_if_exists(startup_file)

                if bot_process.poll() is not None:
                    if shutdown_requested and force:
                        print("Bot stopped after direct shutdown signal. Restarting...")
                        time.sleep(5)
                        bot_process = start_bot(bot_file, working_directory)
                        shutdown_requested = False
                        printed_bot_exit = False
                        printed_waiting = False
                    elif shutdown_requested:
                        if not printed_bot_exit:
                            print("Bot stopped after shutdown signal.")
                            printed_bot_exit = True
                    else:
                        print("Bot exited unexpectedly. Press Enter to start up bot again.")
                        break

                time.sleep(1)

            while True:
                if restart_event.is_set():
                    restart_event.clear()
                    create_empty_file(startup_file)
                    print("startup.txt created.")
                    break
                time.sleep(0.2)
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        shutdown_event.set()
        stop_bot(bot_process)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    run(args.file, args.force)


if __name__ == "__main__":
    main()