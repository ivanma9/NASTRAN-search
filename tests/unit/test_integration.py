"""Integration tests for the ingestion pipeline roundtrip.

Tests the full pipeline: discover → preprocess → chunk → extract metadata → validate.
Embedding and ChromaDB storage are tested with mocks to avoid API calls.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from legacylens.ingest.discovery import discover_fortran_files
from legacylens.ingest.preprocess import preprocess_fixed_form
from legacylens.ingest.chunker import chunk_fortran, FortranChunk
from legacylens.ingest.metadata import extract_metadata


@pytest.fixture
def sample_fortran_dir(tmp_path):
    """Create a temporary directory with realistic FORTRAN files."""
    # File with a subroutine that has COMMON blocks and CALLs
    (tmp_path / "solver.f").write_text(
        "      SUBROUTINE SOLVER(A, B, N)\n"
        "C     SOLVE LINEAR SYSTEM\n"
        "      INTEGER N\n"
        "      REAL A(N,N), B(N)\n"
        "      COMMON /PARAMS/ TOL, MAXITER\n"
        "      COMMON /WORK/ TEMP(100)\n"
        "      CALL DECOMP(A, N)\n"
        "      CALL BACKSUB(A, B, N)\n"
        "      RETURN\n"
        "      END\n"
    )

    # File with a function and ENTRY point
    (tmp_path / "mathlib.f").write_text(
        "      REAL FUNCTION VECNORM(V, N)\n"
        "      INTEGER N\n"
        "      REAL V(N)\n"
        "      REAL SUM\n"
        "      SUM = 0.0\n"
        "      DO 10 I = 1, N\n"
        "         SUM = SUM + V(I)**2\n"
        "   10 CONTINUE\n"
        "      VECNORM = SQRT(SUM)\n"
        "      RETURN\n"
        "      ENTRY VECMAX(V, N)\n"
        "      VECMAX = V(1)\n"
        "      DO 20 I = 2, N\n"
        "         IF (V(I) .GT. VECMAX) VECMAX = V(I)\n"
        "   20 CONTINUE\n"
        "      RETURN\n"
        "      END\n"
    )

    # File with BLOCK DATA
    (tmp_path / "initdata.f").write_text(
        "      BLOCK DATA INITVALS\n"
        "      COMMON /PARAMS/ TOL, MAXITER\n"
        "      DATA TOL /1.0E-6/\n"
        "      DATA MAXITER /100/\n"
        "      END\n"
    )

    # File with continuation lines
    (tmp_path / "longcall.f").write_text(
        "      SUBROUTINE LONGARG(A, B, C,\n"
        "     &                    D, E, F)\n"
        "      REAL A, B, C, D, E, F\n"
        "      CALL HELPER(A,\n"
        "     &             B)\n"
        "      RETURN\n"
        "      END\n"
    )

    return tmp_path


def test_full_pipeline_roundtrip(sample_fortran_dir):
    """Test discover → preprocess → chunk → metadata for all files."""
    # Step 1: Discover files
    files = discover_fortran_files(sample_fortran_dir)
    assert len(files) == 4

    # Step 2-4: Process each file
    all_chunks = []
    for fpath in files:
        text = fpath.read_text()
        preprocessed, line_map = preprocess_fixed_form(text)
        chunks = chunk_fortran(preprocessed, str(fpath), line_map)
        for chunk in chunks:
            extract_metadata(chunk)
            all_chunks.append(chunk)

    # Should have at least one chunk per file
    assert len(all_chunks) >= 4

    # Check that unit names were extracted
    unit_names = {c.unit_name for c in all_chunks if c.unit_name}
    assert "SOLVER" in unit_names
    assert "VECNORM" in unit_names
    assert "INITVALS" in unit_names
    assert "LONGARG" in unit_names


def test_metadata_extraction_in_pipeline(sample_fortran_dir):
    """Verify metadata is correctly populated through the pipeline."""
    files = discover_fortran_files(sample_fortran_dir)
    all_chunks = []
    for fpath in files:
        text = fpath.read_text()
        preprocessed, line_map = preprocess_fixed_form(text)
        chunks = chunk_fortran(preprocessed, str(fpath), line_map)
        for chunk in chunks:
            extract_metadata(chunk)
            all_chunks.append(chunk)

    # Find the SOLVER chunk
    solver = next(c for c in all_chunks if c.unit_name == "SOLVER")
    assert "PARAMS" in solver.common_blocks or "/PARAMS/" in solver.common_blocks
    assert any("DECOMP" in call for call in solver.calls)
    assert any("BACKSUB" in call for call in solver.calls)

    # Find the VECNORM chunk
    vecnorm = next(c for c in all_chunks if c.unit_name == "VECNORM")
    assert "VECMAX" in vecnorm.entry_points

    # Find the INITVALS chunk
    initvals = next(c for c in all_chunks if c.unit_name == "INITVALS")
    assert initvals.unit_type == "block_data"
    assert any("PARAMS" in cb for cb in initvals.common_blocks)


def test_continuation_lines_preserved(sample_fortran_dir):
    """Verify continuation lines are properly joined."""
    longcall = sample_fortran_dir / "longcall.f"
    text = longcall.read_text()
    preprocessed, line_map = preprocess_fixed_form(text)

    # After preprocessing, continuation should be joined
    assert "&" not in preprocessed
    # The subroutine signature should be on one line
    for line in preprocessed.splitlines():
        if "LONGARG" in line:
            assert "D" in line or "E" in line or "F" in line
            break


def test_chunk_token_counts(sample_fortran_dir):
    """Verify all chunks have valid token counts after metadata extraction."""
    files = discover_fortran_files(sample_fortran_dir)
    for fpath in files:
        text = fpath.read_text()
        preprocessed, line_map = preprocess_fixed_form(text)
        chunks = chunk_fortran(preprocessed, str(fpath), line_map)
        for chunk in chunks:
            extract_metadata(chunk)
            assert chunk.token_count > 0


def test_line_numbers_valid(sample_fortran_dir):
    """Verify line_start <= line_end for all chunks."""
    files = discover_fortran_files(sample_fortran_dir)
    for fpath in files:
        text = fpath.read_text()
        preprocessed, line_map = preprocess_fixed_form(text)
        chunks = chunk_fortran(preprocessed, str(fpath), line_map)
        for chunk in chunks:
            assert chunk.line_start <= chunk.line_end, (
                f"Invalid line range in {chunk.unit_name}: "
                f"{chunk.line_start}-{chunk.line_end}"
            )


def test_cross_reference_indices_from_pipeline(sample_fortran_dir):
    """Test that cross-reference indices can be built from pipeline output."""
    from legacylens.index.common_blocks import build_common_block_index
    from legacylens.index.call_graph import build_call_graph

    files = discover_fortran_files(sample_fortran_dir)
    all_chunks = []
    for fpath in files:
        text = fpath.read_text()
        preprocessed, line_map = preprocess_fixed_form(text)
        chunks = chunk_fortran(preprocessed, str(fpath), line_map)
        for chunk in chunks:
            extract_metadata(chunk)
            all_chunks.append(chunk)

    # Build COMMON block index
    cb_index = build_common_block_index(all_chunks)
    # PARAMS should be referenced by both SOLVER and INITVALS
    params_refs = None
    for key in cb_index:
        if "PARAMS" in key:
            params_refs = cb_index[key]
            break
    assert params_refs is not None
    ref_units = {r["unit"] for r in params_refs["referenced_by"]}
    assert "SOLVER" in ref_units
    assert "INITVALS" in ref_units

    # Build call graph
    cg = build_call_graph(all_chunks)
    assert "SOLVER" in cg
    assert any("DECOMP" in c for c in cg["SOLVER"]["calls"])


@patch("legacylens.ingest.embedder.voyageai")
def test_pipeline_with_mocked_embedding(mock_voyage, sample_fortran_dir):
    """Test full pipeline including embedding step with mocked API."""
    from legacylens.ingest.embedder import embed_chunks

    # Mock the Voyage client
    mock_client = MagicMock()
    mock_voyage.Client.return_value = mock_client

    # Collect chunks
    files = discover_fortran_files(sample_fortran_dir)
    all_chunks = []
    for fpath in files:
        text = fpath.read_text()
        preprocessed, line_map = preprocess_fixed_form(text)
        chunks = chunk_fortran(preprocessed, str(fpath), line_map)
        for chunk in chunks:
            extract_metadata(chunk)
            all_chunks.append(chunk)

    # Mock embed response
    mock_response = MagicMock()
    mock_response.embeddings = [[0.1] * 1024 for _ in range(len(all_chunks))]
    mock_response.total_tokens = 500
    mock_client.embed.return_value = mock_response

    with patch("legacylens.ingest.embedder.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            voyage_api_key="test-key",
            embedding_model="voyage-code-3",
        )
        results = embed_chunks(all_chunks)

    assert len(results) == len(all_chunks)
    for chunk, embedding in results:
        assert isinstance(embedding, list)
        assert len(embedding) == 1024
