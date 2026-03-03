"""Tests for COMMON block cross-reference index."""

from legacylens.ingest.chunker import FortranChunk
from legacylens.index.common_blocks import (
    build_common_block_index,
    find_shared_state,
    lookup_common_block,
)


def _make_chunk(name: str, common_blocks: list[str], file: str = "test.f", line: int = 1) -> FortranChunk:
    return FortranChunk(
        text="",
        file_path=file,
        line_start=line,
        line_end=line + 10,
        unit_name=name,
        unit_type="subroutine",
        common_blocks=common_blocks,
    )


class TestBuildIndex:
    def test_single_block_single_unit(self):
        chunks = [_make_chunk("AAA", ["/SYSTEM/"])]
        index = build_common_block_index(chunks)
        assert "/SYSTEM/" in index
        assert len(index["/SYSTEM/"]["referenced_by"]) == 1
        assert index["/SYSTEM/"]["referenced_by"][0]["unit"] == "AAA"

    def test_single_block_multiple_units(self):
        chunks = [
            _make_chunk("AAA", ["/SYSTEM/"], "a.f"),
            _make_chunk("BBB", ["/SYSTEM/"], "b.f"),
        ]
        index = build_common_block_index(chunks)
        assert len(index["/SYSTEM/"]["referenced_by"]) == 2

    def test_multiple_blocks(self):
        chunks = [
            _make_chunk("AAA", ["/SYSTEM/", "/XDATA/"]),
            _make_chunk("BBB", ["/XDATA/"]),
        ]
        index = build_common_block_index(chunks)
        assert len(index) == 2
        assert len(index["/SYSTEM/"]["referenced_by"]) == 1
        assert len(index["/XDATA/"]["referenced_by"]) == 2

    def test_empty_chunks(self):
        index = build_common_block_index([])
        assert index == {}


class TestLookup:
    def test_lookup_existing(self):
        index = {"/SYSTEM/": {"referenced_by": [{"file": "a.f", "unit": "AAA", "line": 1}]}}
        refs = lookup_common_block("/SYSTEM/", index)
        assert len(refs) == 1
        assert refs[0]["unit"] == "AAA"

    def test_lookup_without_slashes(self):
        index = {"/SYSTEM/": {"referenced_by": [{"file": "a.f", "unit": "AAA", "line": 1}]}}
        refs = lookup_common_block("SYSTEM", index)
        assert len(refs) == 1

    def test_lookup_missing(self):
        refs = lookup_common_block("/MISSING/", {})
        assert refs == []


class TestSharedState:
    def test_find_shared_state_from_chunks(self):
        chunks = [
            _make_chunk("AAA", ["/SYSTEM/", "/XDATA/"]),
            _make_chunk("BBB", ["/XDATA/"]),
        ]
        blocks = find_shared_state("AAA", chunks=chunks)
        assert "/SYSTEM/" in blocks
        assert "/XDATA/" in blocks

    def test_find_shared_state_from_index(self):
        index = {
            "/SYSTEM/": {"referenced_by": [{"file": "a.f", "unit": "AAA", "line": 1}]},
            "/XDATA/": {"referenced_by": [{"file": "a.f", "unit": "AAA", "line": 1}]},
        }
        blocks = find_shared_state("AAA", index=index)
        assert "/SYSTEM/" in blocks
        assert "/XDATA/" in blocks
