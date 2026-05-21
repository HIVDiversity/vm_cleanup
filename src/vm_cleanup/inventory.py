import os
import pwd

from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import asdict
from loguru import logger

from vm_cleanup.utils import (
    write_tsv,
    format_gb,
    system_usernames,
    StaleFile,
    JunkFile,
    LargeFile,
)


def audit(data_dir: Path, out_dir: Path, stale_days: int, min_size_mb: int):

    cutoff = datetime.now() - timedelta(days=stale_days)
    min_bytes = min_size_mb * 1024 * 1024

    owner_size_map: defaultdict[str, int] = defaultdict(int)
    owner_count_map: defaultdict[str, int] = defaultdict(int)
    file_type_size_map: defaultdict[str, int] = defaultdict(int)
    file_type_count_map: defaultdict[str, int] = defaultdict(int)

    stale_files = []
    large_files = []
    total_files = 0

    logger.info("Starting Walkthrough")

    for root, _, files in os.walk(data_dir):
        for fname in files:
            total_files += 1
            fpath = Path(root) / fname
            try:
                st = fpath.stat()
                size = fpath.stat().st_size

                uid = st.st_uid
                try:
                    owner = pwd.getpwuid(uid).pw_name
                except KeyError:
                    owner = str(uid)

                ext = fpath.suffix.lstrip(".").lower() or "no_extension"
                mtime = datetime.fromtimestamp(st.st_mtime)

                owner_size_map[owner] += size
                owner_count_map[owner] += 1

                file_type_size_map[ext] += size
                file_type_count_map[ext] += 1

                if mtime < cutoff:
                    stale_files.append(
                        StaleFile(
                            last_modified=mtime.strftime("%Y-%m-%d"),
                            size_bytes=str(size),
                            path=str(fpath),
                        )
                    )

                if size >= min_bytes:
                    large_files.append(
                        LargeFile(extension=ext, size_bytes=size, path=str(fpath))
                    )

            except OSError as os_error:
                logger.error(os_error)

    logger.info("Writing outputs")
    owner_size_output = out_dir / "owner_size.tsv"
    owner_count_output = out_dir / "owner_count.tsv"
    ext_size_output = out_dir / "ext_size.tsv"
    ext_count_output = out_dir / "ext_count.tsv"
    stale_file_output = out_dir / "stale_files.tsv"
    large_file_output = out_dir / "large_files.tsv"

    write_tsv(
        owner_size_output,
        [{"owner": o, "size": owner_size_map[o]} for o in owner_size_map],
        ["owner", "size"],
    )

    write_tsv(
        owner_count_output,
        [{"owner": o, "count": owner_count_map[o]} for o in owner_count_map],
        ["owner", "count"],
    )

    write_tsv(
        ext_size_output,
        [{"ext": o, "size": file_type_size_map[o]} for o in file_type_size_map],
        ["ext", "size"],
    )

    write_tsv(
        ext_count_output,
        [{"ext": o, "count": file_type_count_map[o]} for o in file_type_count_map],
        ["ext", "count"],
    )

    write_tsv(
        stale_file_output,
        [asdict(x) for x in stale_files],
        ["last_modified", "size_bytes", "path"],
    )
    write_tsv(
        large_file_output,
        [asdict(x) for x in large_files],
        ["extension", "size_bytes", "path"],
    )

    logger.success(f"Done. Processed {total_files}")
