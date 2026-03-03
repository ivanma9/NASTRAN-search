import logging
from pathlib import Path

logger = logging.getLogger(__name__)

FORTRAN_EXTENSIONS = {".f", ".for", ".ftn"}


def discover_fortran_files(root_path: Path) -> list[Path]:
    """Recursively find all FORTRAN source files under root_path."""
    if not root_path.exists():
        raise FileNotFoundError(f"Source directory not found: {root_path}")

    files = []
    for ext in FORTRAN_EXTENSIONS:
        files.extend(root_path.rglob(f"*{ext}"))

    files = sorted(set(files))
    logger.info(f"Discovered {len(files)} FORTRAN files in {root_path}")
    return files
