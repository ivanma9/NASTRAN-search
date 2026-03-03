"""Tests for metadata extraction."""

from legacylens.ingest.chunker import FortranChunk
from legacylens.ingest.metadata import extract_metadata


def _make_chunk(text: str) -> FortranChunk:
    return FortranChunk(
        text=text,
        file_path="test.f",
        line_start=1,
        line_end=10,
        unit_name="TEST",
        unit_type="subroutine",
    )


class TestCommonBlockExtraction:
    def test_single_common(self):
        chunk = _make_chunk("      COMMON /SYSTEM/ X, Y, Z")
        extract_metadata(chunk)
        assert chunk.common_blocks == ["/SYSTEM/"]

    def test_multiple_commons(self):
        chunk = _make_chunk(
            "      COMMON /SYSTEM/ X\n      COMMON /XDATA/ A, B"
        )
        extract_metadata(chunk)
        assert "/SYSTEM/" in chunk.common_blocks
        assert "/XDATA/" in chunk.common_blocks

    def test_no_commons(self):
        chunk = _make_chunk("      X = 1")
        extract_metadata(chunk)
        assert chunk.common_blocks == []


class TestCallExtraction:
    def test_single_call(self):
        chunk = _make_chunk("      CALL XREAD(A, B)")
        extract_metadata(chunk)
        assert "XREAD" in chunk.calls

    def test_multiple_calls(self):
        chunk = _make_chunk("      CALL AAA\n      CALL BBB\n      CALL AAA")
        extract_metadata(chunk)
        assert "AAA" in chunk.calls
        assert "BBB" in chunk.calls

    def test_no_calls(self):
        chunk = _make_chunk("      X = 1")
        extract_metadata(chunk)
        assert chunk.calls == []


class TestEntryExtraction:
    def test_entry_point(self):
        chunk = _make_chunk("      ENTRY DCOMP2(X, Y)")
        extract_metadata(chunk)
        assert "DCOMP2" in chunk.entry_points

    def test_no_entry(self):
        chunk = _make_chunk("      X = 1")
        extract_metadata(chunk)
        assert chunk.entry_points == []


class TestIncludeExtraction:
    def test_include(self):
        chunk = _make_chunk("      INCLUDE 'NASNAMES.COM'")
        extract_metadata(chunk)
        assert "NASNAMES.COM" in chunk.includes

    def test_include_double_quotes(self):
        chunk = _make_chunk('      INCLUDE "common.inc"')
        extract_metadata(chunk)
        assert "common.inc" in chunk.includes


class TestExternalExtraction:
    def test_external(self):
        chunk = _make_chunk("      EXTERNAL DABS, DSQRT")
        extract_metadata(chunk)
        assert "DABS" in chunk.externals
        assert "DSQRT" in chunk.externals


class TestCommentRatio:
    def test_all_comments(self):
        chunk = _make_chunk("C     Comment 1\nC     Comment 2")
        extract_metadata(chunk)
        assert chunk.comment_ratio == 1.0

    def test_no_comments(self):
        chunk = _make_chunk("      X = 1\n      Y = 2")
        extract_metadata(chunk)
        assert chunk.comment_ratio == 0.0

    def test_mixed(self):
        chunk = _make_chunk("C     Comment\n      X = 1")
        extract_metadata(chunk)
        assert chunk.comment_ratio == 0.5


class TestTokenCount:
    def test_token_count_set(self):
        chunk = _make_chunk("      SUBROUTINE TEST\n      X = 1\n      END")
        extract_metadata(chunk)
        assert chunk.token_count > 0


class TestRealNastranSnippet:
    def test_nastrn_main(self):
        text = (
            "      PROGRAM NASTRN        \n"
            "C        \n"
            "      CHARACTER*80    VALUE\n"
            "      COMMON / LSTADD / LASTAD\n"
            "      COMMON / SYSTEM / ISYSTM(94),SPERLK\n"
            "      COMMON / ZZZZZZ / IZ(14000000)\n"
            "      INCLUDE 'NASNAMES.COM'\n"
            "      CALL BTSTRP\n"
            "      CALL SECOND (SYSTM(18))\n"
            "      END\n"
        )
        chunk = _make_chunk(text)
        extract_metadata(chunk)
        assert "/LSTADD/" in chunk.common_blocks
        assert "/SYSTEM/" in chunk.common_blocks
        assert "/ZZZZZZ/" in chunk.common_blocks
        assert "BTSTRP" in chunk.calls
        assert "SECOND" in chunk.calls
        assert "NASNAMES.COM" in chunk.includes
