from __future__ import annotations

import pytest

from cursorfleet.adapters.cursor import blocks

BLOCK = blocks.make_block("## Fleet\nhello")


@pytest.mark.parametrize(
    "original",
    ["", "# Title\n", "# Title", "# Title\n\nbody\n", "line1\r\nline2\r\n", "no newline at end"],
)
def test_insert_then_remove_is_byte_identical(original: str) -> None:
    new, prefix = blocks.insert_block(original, BLOCK)
    assert blocks.block_text(new) == BLOCK
    assert blocks.remove_block(new, prefix) == original


def test_idempotent_replace_keeps_surroundings() -> None:
    text, _ = blocks.insert_block("before\n", BLOCK)
    text += "after\n"
    newer = blocks.make_block("changed")
    replaced = blocks.replace_block(text, newer)
    assert replaced.startswith("before\n") and replaced.endswith("after\n")
    assert blocks.block_text(replaced) == newer
    assert blocks.replace_block(replaced, newer) == replaced


def test_crlf_files_get_crlf_blocks() -> None:
    new, _ = blocks.insert_block("a\r\nb\r\n", BLOCK)
    assert "\r\n" in new
    assert "\n" not in new.replace("\r\n", "")
    assert blocks.block_text(new) == BLOCK


def test_remove_without_block_is_noop() -> None:
    assert blocks.remove_block("plain\n", "\n") == "plain\n"


@pytest.mark.parametrize(
    "text",
    [
        blocks.BEGIN + "\nno end",
        blocks.END,
        BLOCK + "\n" + BLOCK,
    ],
)
def test_malformed_markers_raise(text: str) -> None:
    with pytest.raises(blocks.BlockError):
        blocks.find_block(text)
