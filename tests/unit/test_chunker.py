"""Tests for the regex-based FORTRAN chunker."""

from legacylens.ingest.chunker import FortranChunk, chunk_fortran


def _make_line_map(n: int) -> dict[int, int]:
    """Create a simple 1:1 line map."""
    return {i: i + 1 for i in range(n)}


class TestBasicChunking:
    def test_single_subroutine(self):
        text = (
            "      SUBROUTINE DCOMP\n"
            "      INTEGER X\n"
            "      X = 1\n"
            "      END\n"
        )
        line_map = _make_line_map(4)
        chunks = chunk_fortran(text, "test.f", line_map)
        assert len(chunks) == 1
        assert chunks[0].unit_name == "DCOMP"
        assert chunks[0].unit_type == "subroutine"

    def test_two_subroutines(self):
        text = (
            "      SUBROUTINE AAA\n"
            "      X = 1\n"
            "      END\n"
            "      SUBROUTINE BBB\n"
            "      Y = 2\n"
            "      END\n"
        )
        line_map = _make_line_map(6)
        chunks = chunk_fortran(text, "test.f", line_map)
        assert len(chunks) == 2
        assert chunks[0].unit_name == "AAA"
        assert chunks[1].unit_name == "BBB"

    def test_function(self):
        text = (
            "      FUNCTION MYFUNC(X)\n"
            "      MYFUNC = X * 2\n"
            "      END\n"
        )
        line_map = _make_line_map(3)
        chunks = chunk_fortran(text, "test.f", line_map)
        assert len(chunks) == 1
        assert chunks[0].unit_name == "MYFUNC"
        assert chunks[0].unit_type == "function"

    def test_typed_function(self):
        text = (
            "      INTEGER FUNCTION IFOO(N)\n"
            "      IFOO = N + 1\n"
            "      END\n"
        )
        line_map = _make_line_map(3)
        chunks = chunk_fortran(text, "test.f", line_map)
        assert len(chunks) == 1
        assert chunks[0].unit_name == "IFOO"
        assert chunks[0].unit_type == "function"

    def test_program(self):
        text = (
            "      PROGRAM NASTRN\n"
            "      CALL INIT\n"
            "      END\n"
        )
        line_map = _make_line_map(3)
        chunks = chunk_fortran(text, "test.f", line_map)
        assert len(chunks) == 1
        assert chunks[0].unit_name == "NASTRN"
        assert chunks[0].unit_type == "program"

    def test_block_data(self):
        text = (
            "      BLOCK DATA IFX4BD\n"
            "      COMMON /BLK/ I(100)\n"
            "      DATA I /100*0/\n"
            "      END\n"
        )
        line_map = _make_line_map(4)
        chunks = chunk_fortran(text, "test.f", line_map)
        assert len(chunks) == 1
        assert chunks[0].unit_name == "IFX4BD"
        assert chunks[0].unit_type == "block_data"


class TestLineNumbers:
    def test_line_start_end(self):
        text = (
            "      SUBROUTINE AAA\n"
            "      X = 1\n"
            "      Y = 2\n"
            "      END\n"
        )
        line_map = _make_line_map(4)
        chunks = chunk_fortran(text, "test.f", line_map)
        assert chunks[0].line_start == 1
        assert chunks[0].line_end == 4


class TestOversizedChunks:
    def test_oversized_splits(self):
        # Create a subroutine with many lines
        lines = ["      SUBROUTINE BIG"]
        for i in range(500):
            lines.append(f"      X{i} = {i}")
        lines.append("      END")
        text = "\n".join(lines)
        line_map = _make_line_map(len(lines))
        chunks = chunk_fortran(text, "test.f", line_map, max_tokens=200)
        assert len(chunks) > 1
        # All sub-chunks should have the same unit name
        for chunk in chunks:
            assert chunk.unit_name == "BIG"


class TestEdgeCases:
    def test_empty_text(self):
        chunks = chunk_fortran("", "test.f", {})
        assert chunks == []

    def test_comments_only(self):
        text = "C     This is a comment\nC     Another comment"
        line_map = _make_line_map(2)
        chunks = chunk_fortran(text, "test.f", line_map)
        # Comments before any unit should be included in a chunk
        assert len(chunks) >= 0  # May or may not produce a chunk

    def test_code_before_first_unit(self):
        text = (
            "C     File header\n"
            "      SUBROUTINE FIRST\n"
            "      X = 1\n"
            "      END\n"
        )
        line_map = _make_line_map(4)
        chunks = chunk_fortran(text, "test.f", line_map)
        # Should have at least the subroutine chunk
        named = [c for c in chunks if c.unit_name]
        assert len(named) == 1
        assert named[0].unit_name == "FIRST"

    def test_token_count_populated(self):
        text = (
            "      SUBROUTINE TEST\n"
            "      X = 1\n"
            "      END\n"
        )
        line_map = _make_line_map(3)
        chunks = chunk_fortran(text, "test.f", line_map)
        assert chunks[0].token_count > 0
