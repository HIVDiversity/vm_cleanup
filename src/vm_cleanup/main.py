import typer
from pathlib import Path
from loguru import logger

app = typer.Typer()


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


def inventory():
    pass


def main():
    app()


if __name__ == "__main__":
    main()
