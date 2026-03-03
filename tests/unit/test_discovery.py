"""Tests for FORTRAN file discovery."""

import pytest
from pathlib import Path

from legacylens.ingest.discovery import discover_fortran_files, FORTRAN_EXTENSIONS


@pytest.fixture
def fortran_tree(tmp_path):
    """Create a temporary directory with various FORTRAN and non-FORTRAN files."""
    # FORTRAN files
    (tmp_path / "main.f").write_text("      PROGRAM MAIN\n      END\n")
    (tmp_path / "utils.for").write_text("      SUBROUTINE UTILS\n      END\n")
    (tmp_path / "helper.ftn").write_text("      FUNCTION HELPER\n      END\n")

    # Nested directories
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "nested.f").write_text("      SUBROUTINE NESTED\n      END\n")

    deep = sub / "deep"
    deep.mkdir()
    (deep / "deep.f").write_text("      SUBROUTINE DEEP\n      END\n")

    # Non-FORTRAN files (should be ignored)
    (tmp_path / "readme.txt").write_text("readme")
    (tmp_path / "code.c").write_text("int main() {}")
    (tmp_path / "data.dat").write_text("1 2 3")

    return tmp_path


def test_discovers_all_extensions(fortran_tree):
    files = discover_fortran_files(fortran_tree)
    extensions = {f.suffix for f in files}
    assert extensions == {".f", ".for", ".ftn"}


def test_discovers_correct_count(fortran_tree):
    files = discover_fortran_files(fortran_tree)
    assert len(files) == 5


def test_discovers_nested_files(fortran_tree):
    files = discover_fortran_files(fortran_tree)
    names = {f.name for f in files}
    assert "nested.f" in names
    assert "deep.f" in names


def test_ignores_non_fortran(fortran_tree):
    files = discover_fortran_files(fortran_tree)
    names = {f.name for f in files}
    assert "readme.txt" not in names
    assert "code.c" not in names
    assert "data.dat" not in names


def test_returns_sorted_list(fortran_tree):
    files = discover_fortran_files(fortran_tree)
    assert files == sorted(files)


def test_no_duplicates(fortran_tree):
    files = discover_fortran_files(fortran_tree)
    assert len(files) == len(set(files))


def test_raises_on_missing_dir():
    with pytest.raises(FileNotFoundError):
        discover_fortran_files(Path("/nonexistent/path"))


def test_empty_directory(tmp_path):
    files = discover_fortran_files(tmp_path)
    assert files == []


def test_returns_path_objects(fortran_tree):
    files = discover_fortran_files(fortran_tree)
    assert all(isinstance(f, Path) for f in files)
