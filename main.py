"""
main.py — Entry point. Loads config, sets up logging, starts watcher.

Run with:
    python main.py
"""

import logging
import sys
from pathlib import Path


def _configure_logging() -> None:
    """
    Set up the root logger to emit to both stdout and pipeline.log.
    All pipeline modules use child loggers (logging.getLogger(__name__))
    so they inherit this configuration automatically.
    """
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Stdout handler — useful for interactive / foreground development
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.INFO)
    stdout_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))

    # File handler — persists across restarts for debugging
    log_file = Path(__file__).parent / "pipeline.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))

    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(file_handler)


def main() -> None:
    _configure_logging()

    logger = logging.getLogger(__name__)
    logger.info("Obsidian Audio Pipeline starting up")

    # Config must load before anything else — all modules receive it as a
    # parameter rather than importing it globally (convention from CLAUDE.md).
    try:
        from config import load_config
        config = load_config()
    except Exception as exc:
        # Use print here as a fallback — logging may not be fully wired yet
        # if the import itself fails, though _configure_logging() runs first.
        logging.getLogger(__name__).error(
            "Failed to load configuration: %s", exc, exc_info=True
        )
        sys.exit(1)

    logger.info(
        "Config loaded — watching '%s', vault inbox '%s'",
        config["watch_folder"],
        config["obsidian_vault_folder"],
    )

    # Import watcher only after config is confirmed good so that import errors
    # in watcher.py (e.g. missing watchdog) surface with a clear log message.
    try:
        from watcher import start_watcher
    except ImportError as exc:
        logger.error(
            "Could not import watcher module: %s. "
            "Ensure all dependencies are installed: pip install -r requirements.txt",
            exc,
            exc_info=True,
        )
        sys.exit(1)

    try:
        start_watcher(config)
    except KeyboardInterrupt:
        logger.info("Shutting down — KeyboardInterrupt received")
        sys.exit(0)
    except Exception as exc:
        logger.error("Watcher crashed unexpectedly: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
