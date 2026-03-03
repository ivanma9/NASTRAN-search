"""Tests against actual NASTRAN-95 files from the cloned repo.

These tests verify the pipeline works on real NASTRAN-95 source code,
not just synthetic fixtures. Skipped if the NASTRAN-95 repo is not present.
"""

import pytest
from pathlib import Path

from legacylens.ingest.discovery import discover_fortran_files
from legacylens.ingest.preprocess import preprocess_fixed_form
from legacylens.ingest.chunker import chunk_fortran
from legacylens.ingest.metadata import extract_metadata

NASTRAN_ROOT = Path(__file__).parent.parent.parent / "NASTRAN-95"

nastran_available = pytest.mark.skipif(
    not NASTRAN_ROOT.exists(),
    reason="NASTRAN-95 repo not cloned",
)


@nastran_available
class TestNastranDiscovery:
    def test_discovers_nastran_files(self):
        files = discover_fortran_files(NASTRAN_ROOT)
        # NASTRAN-95 should have 1800+ .f files
        assert len(files) > 1000, f"Expected >1000 files, got {len(files)}"

    def test_all_files_are_fortran(self):
        files = discover_fortran_files(NASTRAN_ROOT)
        for f in files:
            assert f.suffix in {".f", ".for", ".ftn"}, f"Non-FORTRAN file: {f}"

    def test_files_are_readable(self):
        files = discover_fortran_files(NASTRAN_ROOT)
        for f in files[:50]:  # Check first 50
            text = f.read_text(errors="replace")
            assert len(text) > 0, f"Empty file: {f}"


@nastran_available
class TestNastranPreprocessing:
    def _get_sample_files(self, n=20):
        files = discover_fortran_files(NASTRAN_ROOT)
        # Pick files from different directories for variety
        source_files = [f for f in files if "source" in str(f).lower()]
        return source_files[:n] if len(source_files) >= n else files[:n]

    def test_preprocess_does_not_crash(self):
        for fpath in self._get_sample_files():
            text = fpath.read_text(errors="replace")
            preprocessed, line_map = preprocess_fixed_form(text)
            assert isinstance(preprocessed, str)
            assert isinstance(line_map, dict)

    def test_preprocessed_is_uppercase(self):
        for fpath in self._get_sample_files(5):
            text = fpath.read_text(errors="replace")
            preprocessed, _ = preprocess_fixed_form(text)
            # Non-comment, non-empty lines should be uppercase
            for line in preprocessed.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("C") and not stripped.startswith("*"):
                    # Allow digits, punctuation, etc.
                    alpha_chars = [c for c in stripped if c.isalpha()]
                    if alpha_chars:
                        assert all(c.isupper() for c in alpha_chars), (
                            f"Non-uppercase line in {fpath.name}: {stripped[:60]}"
                        )


@nastran_available
class TestNastranChunking:
    def _process_file(self, fpath):
        text = fpath.read_text(errors="replace")
        preprocessed, line_map = preprocess_fixed_form(text)
        return chunk_fortran(preprocessed, str(fpath), line_map)

    def _get_source_files(self, n=20):
        files = discover_fortran_files(NASTRAN_ROOT)
        source = [f for f in files if "source" in str(f).lower()]
        return source[:n] if len(source) >= n else files[:n]

    def test_chunking_produces_output(self):
        total_chunks = 0
        for fpath in self._get_source_files():
            chunks = self._process_file(fpath)
            total_chunks += len(chunks)
        assert total_chunks > 0

    def test_no_empty_chunks(self):
        for fpath in self._get_source_files():
            chunks = self._process_file(fpath)
            for chunk in chunks:
                assert len(chunk.text.strip()) >= 10, (
                    f"Near-empty chunk in {fpath.name}: {repr(chunk.text[:50])}"
                )

    def test_chunks_have_valid_line_ranges(self):
        for fpath in self._get_source_files():
            chunks = self._process_file(fpath)
            for chunk in chunks:
                assert chunk.line_start <= chunk.line_end
                assert chunk.line_start > 0

    def test_most_chunks_have_unit_names(self):
        named = 0
        total = 0
        for fpath in self._get_source_files():
            chunks = self._process_file(fpath)
            for chunk in chunks:
                total += 1
                if chunk.unit_name:
                    named += 1
        # At least 80% of chunks should have unit names
        assert named / total > 0.8 if total > 0 else True, (
            f"Only {named}/{total} chunks have unit names"
        )

    def test_unit_types_are_valid(self):
        valid_types = {"subroutine", "function", "program", "block_data", ""}
        for fpath in self._get_source_files():
            chunks = self._process_file(fpath)
            for chunk in chunks:
                assert chunk.unit_type in valid_types, (
                    f"Invalid unit_type '{chunk.unit_type}' in {fpath.name}"
                )


@nastran_available
class TestNastranMetadata:
    def _process_with_metadata(self, fpath):
        text = fpath.read_text(errors="replace")
        preprocessed, line_map = preprocess_fixed_form(text)
        chunks = chunk_fortran(preprocessed, str(fpath), line_map)
        for chunk in chunks:
            extract_metadata(chunk)
        return chunks

    def _get_source_files(self, n=20):
        files = discover_fortran_files(NASTRAN_ROOT)
        source = [f for f in files if "source" in str(f).lower()]
        return source[:n] if len(source) >= n else files[:n]

    def test_metadata_extraction_does_not_crash(self):
        for fpath in self._get_source_files():
            chunks = self._process_with_metadata(fpath)
            assert isinstance(chunks, list)

    def test_token_counts_are_positive(self):
        for fpath in self._get_source_files(5):
            chunks = self._process_with_metadata(fpath)
            for chunk in chunks:
                assert chunk.token_count > 0

    def test_comment_ratio_in_range(self):
        for fpath in self._get_source_files(5):
            chunks = self._process_with_metadata(fpath)
            for chunk in chunks:
                assert 0.0 <= chunk.comment_ratio <= 1.0

    def test_some_chunks_have_calls(self):
        """NASTRAN-95 code makes extensive use of CALL statements."""
        all_calls = []
        for fpath in self._get_source_files():
            chunks = self._process_with_metadata(fpath)
            for chunk in chunks:
                all_calls.extend(chunk.calls)
        assert len(all_calls) > 0, "No CALL statements found in NASTRAN-95 files"

    def test_some_chunks_have_common_blocks(self):
        """NASTRAN-95 uses COMMON blocks heavily for shared state."""
        all_commons = []
        for fpath in self._get_source_files():
            chunks = self._process_with_metadata(fpath)
            for chunk in chunks:
                all_commons.extend(chunk.common_blocks)
        assert len(all_commons) > 0, "No COMMON blocks found in NASTRAN-95 files"
