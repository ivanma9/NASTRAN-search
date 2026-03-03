"""Tests for the fixed-form FORTRAN preprocessor."""

from legacylens.ingest.preprocess import preprocess_fixed_form


class TestContinuationJoining:
    def test_no_continuations(self):
        text = "      X = 1\n      Y = 2"
        result, line_map = preprocess_fixed_form(text)
        lines = result.splitlines()
        assert len(lines) == 2
        assert "X = 1" in lines[0]
        assert "Y = 2" in lines[1]

    def test_single_continuation(self):
        text = "      X = A + B +\n     1    C + D"
        result, line_map = preprocess_fixed_form(text)
        lines = result.splitlines()
        # Continuation should be joined
        assert len(lines) == 1
        assert "X = A + B +" in lines[0]
        assert "C + D" in lines[0]

    def test_multiple_continuations(self):
        text = "      COMMON /BLK/ A,\n     1  B,\n     2  C"
        result, line_map = preprocess_fixed_form(text)
        lines = result.splitlines()
        assert len(lines) == 1
        assert "A," in lines[0]
        assert "B," in lines[0]
        assert "C" in lines[0]

    def test_continuation_with_ampersand(self):
        """Column 6 with '&' should be treated as continuation."""
        text = "      X = A +\n     &    B"
        result, _ = preprocess_fixed_form(text)
        lines = result.splitlines()
        assert len(lines) == 1


class TestCommentHandling:
    def test_c_comment(self):
        text = "C     This is a comment\n      X = 1"
        result, _ = preprocess_fixed_form(text)
        lines = result.splitlines()
        assert lines[0].startswith("C")
        assert len(lines) == 2

    def test_lowercase_c_comment(self):
        text = "c     This is a comment"
        result, _ = preprocess_fixed_form(text)
        assert result.startswith("C")

    def test_star_comment(self):
        text = "*     Star comment\n      X = 1"
        result, _ = preprocess_fixed_form(text)
        assert result.splitlines()[0].startswith("*")

    def test_comment_not_joined_as_continuation(self):
        text = "      X = 1\nC     Comment line\n      Y = 2"
        result, _ = preprocess_fixed_form(text)
        lines = result.splitlines()
        assert len(lines) == 3


class TestCaseNormalization:
    def test_uppercase_conversion(self):
        text = "      subroutine test\n      integer x"
        result, _ = preprocess_fixed_form(text)
        assert "SUBROUTINE TEST" in result
        assert "INTEGER X" in result


class TestLineMapping:
    def test_simple_mapping(self):
        text = "      X = 1\n      Y = 2\n      Z = 3"
        _, line_map = preprocess_fixed_form(text)
        assert line_map[0] == 1
        assert line_map[1] == 2
        assert line_map[2] == 3

    def test_continuation_mapping(self):
        text = "      X = A +\n     1    B\n      Y = 2"
        _, line_map = preprocess_fixed_form(text)
        # First preprocessed line maps to original line 1
        assert line_map[0] == 1
        # Second preprocessed line maps to original line 3 (Y = 2)
        assert line_map[1] == 3

    def test_empty_lines(self):
        text = "\n      X = 1\n\n      Y = 2"
        _, line_map = preprocess_fixed_form(text)
        assert line_map[0] == 1  # empty line
        assert line_map[1] == 2  # X = 1


class TestRealNastranSnippet:
    def test_nastran_program_header(self):
        """Test with a real NASTRAN-95 snippet."""
        text = (
            "      PROGRAM NASTRN        \n"
            "C        \n"
            "      CHARACTER*80    VALUE\n"
            "      CHARACTER*5     TMP\n"
            "      INTEGER         SPERLK\n"
            "      REAL            SYSTM(94)\n"
            "      COMMON / LSTADD / LASTAD\n"
            "      COMMON / SYSTEM / ISYSTM(94),SPERLK\n"
        )
        result, line_map = preprocess_fixed_form(text)
        assert "PROGRAM NASTRN" in result
        assert "COMMON / LSTADD / LASTAD" in result.upper()
        assert "COMMON / SYSTEM /" in result.upper()
