"""Fixed-form FORTRAN preprocessor.

Handles continuation lines (column 6 non-blank), comment detection,
case normalization, and original line number tracking.
"""


def preprocess_fixed_form(text: str) -> tuple[str, dict[int, int]]:
    """Preprocess fixed-form FORTRAN source text.

    Returns:
        tuple of (preprocessed_text, line_map) where line_map maps
        preprocessed line number (0-indexed) to original line number (1-indexed).
    """
    raw_lines = text.splitlines()
    output_lines: list[str] = []
    line_map: dict[int, int] = {}  # preprocessed line idx -> original line number

    i = 0
    while i < len(raw_lines):
        line = raw_lines[i]
        orig_line_num = i + 1

        # Empty line — keep as-is
        if not line.strip():
            line_map[len(output_lines)] = orig_line_num
            output_lines.append("")
            i += 1
            continue

        # Comment line: C, c, *, or ! in column 1
        if len(line) > 0 and line[0] in ("C", "c", "*", "!"):
            line_map[len(output_lines)] = orig_line_num
            output_lines.append(line.upper())
            i += 1
            continue

        # Regular statement — collect continuation lines
        stmt = line
        line_map[len(output_lines)] = orig_line_num
        i += 1

        # Check for continuation lines (column 6 is non-blank and not '0' or ' ')
        while i < len(raw_lines):
            next_line = raw_lines[i]
            if len(next_line) > 5 and next_line[0] not in ("C", "c", "*", "!") and next_line[5] not in (" ", "0", ""):
                # Continuation line — append columns 7+ to current statement
                continuation = next_line[6:] if len(next_line) > 6 else ""
                stmt = stmt + continuation
                i += 1
            else:
                break

        output_lines.append(stmt.upper())

    return "\n".join(output_lines), line_map
