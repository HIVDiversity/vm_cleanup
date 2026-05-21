from datetime import datetime
from pathlib import Path

import typer
from loguru import logger

from vm_cleanup import utils, inventory

app = typer.Typer(add_completion=False)


@app.command("inventory")
def inventory_command(
    data_dir: Path = typer.Argument(
        ...,
        help="Root directory to audit (e.g. /data)",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    out_dir: Path = typer.Option(
        None,
        "--out-dir",
        "-o",
        help="Directory to write TSV reports into. Defaults to ./audit_<timestamp>",
    ),
    stale_days: int = typer.Option(
        730,
        "--stale-days",
        "-s",
        help="Files not modified in this many days are considered stale.",
        min=1,
    ),
    min_size_mb: int = typer.Option(
        100,
        "--min-size-mb",
        "-m",
        help="Minimum file size (MB) for uncompressed large-file scan.",
        min=1,
    ),
    orphan_depth: int = typer.Option(
        3,
        "--orphan-depth",
        "-d",
        help="Directory depth to scan for orphaned owners.",
        min=1,
    ),
    log_file: Path = typer.Option(
        None,
        "--log-file",
        "-l",
        help="Optional path to write a log file.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable debug-level logging.",
    ),
):
    """
    Audit a lab storage directory and produce TSV reports.

    Example:\n
        python audit_storage.py /data --out-dir ./reports --stale-days 365 --verbose
    """
    utils.configure_logging(log_file, verbose)

    # Resolve output directory
    if out_dir is None:
        out_dir = Path(f"./audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Starting storage audit")
    logger.info(f"  Source : {data_dir.resolve()}")
    logger.info(f"  Output : {out_dir.resolve()}")
    logger.info(f"  Stale threshold : {stale_days} days")
    logger.info(f"  Min size (uncompressed scan) : {min_size_mb} MB")

    start = datetime.now()

    inventory.audit(data_dir, out_dir, stale_days, min_size_mb)

    elapsed = datetime.now() - start
    logger.success(f"Audit complete in {elapsed}. Reports in: {out_dir.resolve()}")

    pass


def main():
    app()


if __name__ == "__main__":
    main()
