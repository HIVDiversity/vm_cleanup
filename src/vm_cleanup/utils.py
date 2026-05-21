import typer
from pathlib import Path
from loguru import logger
import csv
import pwd


def write_tsv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    logger.debug(f"  Written: {path} ({len(rows)} rows)")


def system_usernames() -> set[str]:
    """Return all usernames present in /etc/passwd."""
    return {entry.pw_name for entry in pwd.getpwall()}


def format_gb(size_bytes: int) -> str:
    return f"{size_bytes / 1024**3:.3f}"


def configure_logging(log_file: Path | None, verbose: bool) -> None:
    """Set up loguru: stderr + optional file sink."""
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(
        lambda msg: typer.echo(msg, err=True),
        level=level,
        colorize=True,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
    )
    if log_file:
        logger.add(
            log_file,
            level="DEBUG",
            rotation="10 MB",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message}",
        )
        logger.debug(f"Logging to file: {log_file}")
