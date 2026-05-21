import os
import pwd

from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

from vm_cleanup.utils import write_tsv, format_gb, system_usernames


def audit_files_by_year(data_dir: Path, out_dir: Path) -> None:
    logger.info("[ 1 / 7 ] Counting files by last-modified year …")
    counts: defaultdict[str, int] = defaultdict(int)
    total = 0

    for root, _, files in os.walk(data_dir):
        for fname in files:
            fpath = Path(root) / fname
            try:
                year = datetime.fromtimestamp(fpath.stat().st_mtime).strftime("%Y")
                counts[year] += 1
                total += 1
            except OSError:
                pass

    rows = [{"year": y, "file_count": c} for y, c in sorted(counts.items())]
    write_tsv(out_dir / "files_by_year.tsv", rows, ["year", "file_count"])
    logger.success(f"  Files by year: {total:,} files across {len(counts)} years")


def audit_usage_by_owner(data_dir: Path, out_dir: Path) -> None:
    logger.info("[ 2 / 7 ] Calculating disk usage per owner …")
    size_map: defaultdict[str, int] = defaultdict(int)
    count_map: defaultdict[str, int] = defaultdict(int)

    for root, _, files in os.walk(data_dir):
        for fname in files:
            fpath = Path(root) / fname
            try:
                st = fpath.stat()
                try:
                    owner = pwd.getpwuid(st.st_uid).pw_name
                except KeyError:
                    owner = str(st.st_uid)
                size_map[owner] += st.st_size
                count_map[owner] += 1
            except OSError:
                pass

    rows = sorted(
        [
            {"owner": o, "size_gb": format_gb(size_map[o]), "file_count": count_map[o]}
            for o in size_map
        ],
        key=lambda r: float(r["size_gb"]),
        reverse=True,
    )
    write_tsv(out_dir / "usage_by_owner.tsv", rows, ["owner", "size_gb", "file_count"])
    logger.success(f"  Owners found: {len(rows)}")


def audit_file_types(data_dir: Path, out_dir: Path) -> None:
    logger.info("[ 3 / 7 ] Analysing file types by extension …")
    size_map: defaultdict[str, int] = defaultdict(int)
    count_map: defaultdict[str, int] = defaultdict(int)

    for root, _, files in os.walk(data_dir):
        for fname in files:
            fpath = Path(root) / fname
            ext = fpath.suffix.lstrip(".").lower() or "no_extension"
            try:
                size_map[ext] += fpath.stat().st_size
                count_map[ext] += 1
            except OSError:
                pass

    rows = sorted(
        [
            {
                "extension": e,
                "size_gb": format_gb(size_map[e]),
                "file_count": count_map[e],
            }
            for e in size_map
        ],
        key=lambda r: float(r["size_gb"]),
        reverse=True,
    )
    write_tsv(out_dir / "file_types.tsv", rows, ["extension", "size_gb", "file_count"])

    # Highlight key bioinformatics extensions
    bio_exts = {
        "bam",
        "sam",
        "cram",
        "fastq",
        "fq",
        "vcf",
        "bcf",
        "tif",
        "tiff",
        "nd2",
        "czi",
        "fasta",
        "fa",
    }
    found_bio = {r["extension"]: r for r in rows if r["extension"] in bio_exts}
    if found_bio:
        bio_gb = sum(float(r["size_gb"]) for r in found_bio.values())
        logger.success(
            f"  {len(found_bio)} bioinformatics extension(s) found — {bio_gb:.2f} GB total"
        )
    logger.success(f"  Unique extensions: {len(rows)}")


def audit_stale_files(data_dir: Path, out_dir: Path, stale_days: int) -> None:
    logger.info(f"[ 4 / 7 ] Finding files not modified in >{stale_days} days …")
    cutoff = datetime.now() - timedelta(days=stale_days)
    rows = []

    for root, _, files in os.walk(data_dir):
        for fname in files:
            fpath = Path(root) / fname
            try:
                st = fpath.stat()
                mtime = datetime.fromtimestamp(st.st_mtime)
                if mtime < cutoff:
                    rows.append(
                        {
                            "last_modified": mtime.strftime("%Y-%m-%d"),
                            "size_bytes": st.st_size,
                            "size_gb": format_gb(st.st_size),
                            "path": str(fpath),
                        }
                    )
            except OSError:
                pass

    rows.sort(key=lambda r: r["last_modified"])
    write_tsv(
        out_dir / "stale_files.tsv",
        rows,
        ["last_modified", "size_bytes", "size_gb", "path"],
    )
    total_gb = sum(int(r["size_bytes"]) for r in rows) / 1024**3
    logger.success(f"  Stale files: {len(rows):,} files — {total_gb:.2f} GB")


def audit_orphaned_dirs(data_dir: Path, out_dir: Path, max_depth: int) -> None:
    logger.info("[ 5 / 7 ] Detecting directories owned by absent system users …")
    known_users = system_usernames()
    rows = []

    def _walk(path: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            for entry in path.iterdir():
                if entry.is_dir():
                    try:
                        uid = entry.stat().st_uid
                        try:
                            owner = pwd.getpwuid(uid).pw_name
                        except KeyError:
                            owner = str(uid)
                        if owner not in known_users:
                            rows.append({"owner": owner, "directory": str(entry)})
                    except OSError:
                        pass
                    _walk(entry, depth + 1)
        except PermissionError:
            pass

    _walk(data_dir, 1)
    write_tsv(out_dir / "orphaned_dirs.tsv", rows, ["owner", "directory"])
    logger.success(f"  Orphaned directories: {len(rows)}")


def audit_uncompressed_large(data_dir: Path, out_dir: Path, min_size_mb: int) -> None:
    logger.info(f"[ 6 / 7 ] Finding uncompressed files >{min_size_mb} MB …")
    target_exts = {
        "fastq",
        "fq",
        "sam",
        "fasta",
        "fa",
        "txt",
        "csv",
        "tsv",
        "bed",
        "gtf",
        "gff",
        "gff3",
        "wig",
        "bedgraph",
    }
    min_bytes = min_size_mb * 1024 * 1024
    rows = []

    for root, _, files in os.walk(data_dir):
        for fname in files:
            fpath = Path(root) / fname
            ext = fpath.suffix.lstrip(".").lower()
            if ext not in target_exts:
                continue
            try:
                size = fpath.stat().st_size
                if size >= min_bytes:
                    rows.append(
                        {
                            "extension": ext,
                            "size_gb": format_gb(size),
                            "path": str(fpath),
                        }
                    )
            except OSError:
                pass

    rows.sort(key=lambda r: float(r["size_gb"]), reverse=True)
    write_tsv(
        out_dir / "uncompressed_large.tsv", rows, ["extension", "size_gb", "path"]
    )
    total_gb = sum(float(r["size_gb"]) for r in rows)
    logger.success(f"  Uncompressed large files: {len(rows):,} — {total_gb:.2f} GB")


def audit_junk_files(data_dir: Path, out_dir: Path) -> None:
    logger.info("[ 7 / 7 ] Scanning for junk/temp files …")
    junk_patterns = {
        "*.tmp",
        "*.temp",
        "*.swp",
        "*.swo",
        "*.bak",
        ".DS_Store",
        "Thumbs.db",
        "core",
        "*.core",
    }
    rows = []

    for root, dirs, files in os.walk(data_dir):
        # Also catch empty dirs
        for fname in files:
            fpath = Path(root) / fname
            matched = any(fpath.match(p) for p in junk_patterns)
            if matched:
                try:
                    size = fpath.stat().st_size
                    rows.append(
                        {
                            "pattern_matched": fname,
                            "size_bytes": size,
                            "path": str(fpath),
                        }
                    )
                except OSError:
                    pass

    rows.sort(key=lambda r: r["size_bytes"], reverse=True)
    write_tsv(
        out_dir / "junk_files.tsv", rows, ["pattern_matched", "size_bytes", "path"]
    )
    total_gb = sum(r["size_bytes"] for r in rows) / 1024**3
    logger.success(f"  Junk files: {len(rows):,} — {total_gb:.3f} GB")


def write_summary(
    out_dir: Path, data_dir: Path, stale_days: int, min_size_mb: int
) -> None:
    summary_path = out_dir / "summary.txt"
    tsv_files = list(out_dir.glob("*.tsv"))
    with open(summary_path, "w") as f:
        f.write("Lab Storage Audit Report\n")
        f.write("========================\n")
        f.write(f"Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Target    : {data_dir}\n")
        f.write(f"Stale days: {stale_days}\n")
        f.write(f"Min size  : {min_size_mb} MB (uncompressed scan)\n\n")
        f.write("Output files:\n")
        for tsv in sorted(tsv_files):
            line_count = sum(1 for _ in open(tsv)) - 1  # subtract header
            f.write(f"  {tsv.name:<35} {line_count:>8} rows\n")
    logger.info(f"Summary written to {summary_path}")
