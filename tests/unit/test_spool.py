from __future__ import annotations

import multiprocessing
import os
import stat
import zlib
from pathlib import Path

import pytest

from cursorfleet.state.runtime import RuntimePaths, runtime_paths
from cursorfleet.state.spool import (
    CAPPED_MARKER,
    MAX_LINE_BYTES,
    append_event,
    decode_line,
    encode_line,
    session_dir,
    writer_file,
)
from cursorfleet.state.spool_read import (
    list_spool_files,
    peek_fingerprint,
    read_all,
    read_file,
)
from m2_helpers import append_worker, dump, make_event

NOW = 1_790_000_000_000


@pytest.fixture
def paths(tmp_path: Path) -> RuntimePaths:
    return runtime_paths(tmp_path / "common" / "cursorfleet")


def put(paths: RuntimePaths, session: str, n: int, writer: str = "main", **kw: object) -> bool:
    return append_event(paths, session, writer, dump(make_event(session, n)), now_ms=NOW + n, **kw)  # type: ignore[arg-type]


# ------------------------------------------------------------------ codec


def test_codec_roundtrip_and_crc() -> None:
    line = encode_line('{"a":1}')
    assert line.endswith(b"\n") and line[8:9] == b" "
    assert decode_line(line[:-1]) == '{"a":1}'
    flipped = line[:-2] + b"X"  # change the last body byte, keep the old CRC
    assert decode_line(flipped) is None


@pytest.mark.parametrize("bad", [b"", b"short", b"zzzzzzzz {}", b"0000000 {}", b"00000000-{}"])
def test_decode_rejects_malformed(bad: bytes) -> None:
    assert decode_line(bad) is None


def test_decode_rejects_non_utf8_with_valid_crc() -> None:
    body = b"\xff\xfe"
    line = b"%08x %s" % (zlib.crc32(body), body)
    assert decode_line(line) is None


def test_oversize_event_is_not_written(paths: RuntimePaths) -> None:
    huge = dump(make_event("s1", 1, paths=[{"path": "a" * 9000}]))
    with pytest.raises(ValueError, match="8 KiB"):
        encode_line(huge)
    assert append_event(paths, "s1", "main", huge, now_ms=NOW) is False
    assert list_spool_files(paths) == []
    assert MAX_LINE_BYTES == 8192


# ------------------------------------------------------------------ append


def test_append_creates_private_layout(paths: RuntimePaths) -> None:
    assert put(paths, "s1", 1)
    assert Path(paths.layout).read_text(encoding="utf-8").strip() == "1"
    file = writer_file(paths, "s1", "main")
    assert os.path.isfile(file) and os.path.dirname(file) == session_dir(paths, "s1")
    if os.name == "posix":
        assert stat.S_IMODE(os.stat(paths.root).st_mode) == 0o700
        assert stat.S_IMODE(os.stat(paths.spool).st_mode) == 0o700
        assert stat.S_IMODE(os.stat(session_dir(paths, "s1")).st_mode) == 0o700
        assert stat.S_IMODE(os.stat(file).st_mode) == 0o600


def test_permissions_ignore_a_permissive_umask(paths: RuntimePaths) -> None:
    if os.name != "posix":
        pytest.skip("POSIX permission bits")
    old = os.umask(0)
    try:
        assert put(paths, "s1", 1)
    finally:
        os.umask(old)
    assert stat.S_IMODE(os.stat(writer_file(paths, "s1", "main")).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(session_dir(paths, "s1")).st_mode) == 0o700


def test_events_roundtrip_per_writer(paths: RuntimePaths) -> None:
    for n in range(5):
        assert put(paths, "s1", n, writer="main")
    for n in range(5, 8):
        assert put(paths, "s1", n, writer="sub-1")
    events, corruption, files = read_all(paths, "s1")
    assert files == 2 and corruption.total == 0
    assert sorted(e.event_id for e in events) == sorted(
        make_event("s1", n)["event_id"] for n in range(8)
    )


def test_unsafe_names_map_to_safe_file_names(paths: RuntimePaths) -> None:
    for session in ("../../etc", "a/b", "CON", "x:y", "trailing."):
        put(paths, session, 1, writer="..")
    for file in list_spool_files(paths):
        assert os.path.realpath(file).startswith(os.path.realpath(paths.spool) + os.sep)


def test_rotation_keeps_every_event(paths: RuntimePaths) -> None:
    for n in range(40):
        assert put(paths, "s1", n, rotate_bytes=3000)
    files = list_spool_files(paths, "s1")
    assert len(files) > 2
    assert any(".jsonl" in f and "main." in os.path.basename(f) for f in files)
    events, corruption, _ = read_all(paths, "s1")
    assert len(events) == 40 and corruption.total == 0


def test_rotated_file_keeps_its_fingerprint(paths: RuntimePaths) -> None:
    put(paths, "s1", 1)
    live = writer_file(paths, "s1", "main")
    before = peek_fingerprint(live)
    assert before is not None
    put(paths, "s1", 2, rotate_bytes=10)  # forces rotation of the file holding event 1
    rotated = [f for f in list_spool_files(paths, "s1") if f != live]
    assert len(rotated) == 1 and peek_fingerprint(rotated[0]) == before


def test_rotation_never_clobbers_a_previous_rotation(paths: RuntimePaths) -> None:
    for n in range(10):  # same timestamp for every append => same rotation target name
        append_event(paths, "s1", "main", dump(make_event("s1", n)), now_ms=NOW, rotate_bytes=10)
    events, _c, _f = read_all(paths, "s1")
    assert len(events) == 10


def test_session_cap_sets_marker_and_stops(paths: RuntimePaths) -> None:
    cap = 2500
    results = [put(paths, "s1", n, rotate_bytes=900, max_session_bytes=cap) for n in range(30)]
    assert results[0] is True and results[-1] is False
    marker = os.path.join(session_dir(paths, "s1"), CAPPED_MARKER)
    assert os.path.exists(marker)
    count_after = len(read_all(paths, "s1")[0])
    assert put(paths, "s1", 99, max_session_bytes=cap) is False
    assert len(read_all(paths, "s1")[0]) == count_after
    assert put(paths, "other", 1) is True  # other sessions are unaffected


def test_short_write_is_terminated_with_newline(
    paths: RuntimePaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    put(paths, "s1", 1)
    real_write = os.write
    state = {"first": True}

    def short_write(fd: int, data: bytes) -> int:
        if state["first"] and len(data) > 20:
            state["first"] = False
            return real_write(fd, data[:15])
        return real_write(fd, data)

    monkeypatch.setattr(os, "write", short_write)
    assert put(paths, "s1", 2) is False
    monkeypatch.undo()
    assert put(paths, "s1", 3) is True
    events, corruption, _ = read_all(paths, "s1")
    assert {e.event_id for e in events} == {
        make_event("s1", 1)["event_id"],
        make_event("s1", 3)["event_id"],
    }
    assert corruption.bad_format + corruption.bad_crc == 1  # the fragment, nothing else lost


def test_append_to_unwritable_location_returns_false(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    bad = RuntimePaths(str(blocker / "cursorfleet"))
    assert append_event(bad, "s1", "main", dump(make_event("s1", 1)), now_ms=NOW) is False


def test_symlinked_writer_file_is_refused(paths: RuntimePaths, tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("O_NOFOLLOW is POSIX")
    put(paths, "s1", 1)
    victim = tmp_path / "victim.txt"
    victim.write_text("keep", encoding="utf-8")
    live = writer_file(paths, "s1", "main")
    os.remove(live)
    os.symlink(victim, live)
    assert put(paths, "s1", 2) is False
    assert victim.read_text(encoding="utf-8") == "keep"


# ------------------------------------------------------------------ reader robustness


def write_raw(paths: RuntimePaths, session: str, data: bytes, writer: str = "main") -> str:
    put(paths, session, 0, writer=writer)  # creates dirs with correct modes
    file = writer_file(paths, session, writer)
    with open(file, "wb") as handle:
        handle.write(data)
    return file


def good_line(session: str, n: int) -> bytes:
    return encode_line(dump(make_event(session, n)))


def test_torn_tail_is_retried_then_read(paths: RuntimePaths) -> None:
    first, second = good_line("s1", 1), good_line("s1", 2)
    file = write_raw(paths, "s1", first + second[:30])
    partial = read_file(file)
    assert [e.event_id for e in partial.events] == [make_event("s1", 1)["event_id"]]
    assert partial.new_offset == len(first) and partial.torn_tail_bytes == 30
    assert partial.corruption.torn_tail == 0  # incremental readers wait for the writer
    with open(file, "ab") as handle:
        handle.write(second[30:])
    rest = read_file(file, partial.new_offset)
    assert [e.event_id for e in rest.events] == [make_event("s1", 2)["event_id"]]
    assert rest.corruption.total == 0


def test_final_read_counts_torn_tail(paths: RuntimePaths) -> None:
    file = write_raw(paths, "s1", good_line("s1", 1) + good_line("s1", 2)[:40])
    result = read_file(file, final=True)
    assert len(result.events) == 1 and result.corruption.torn_tail == 1


def test_garbled_prefix_resyncs_to_the_next_good_record(paths: RuntimePaths) -> None:
    garbage = b'12ab34cd {"schema_version":"1.0","event_id":"01J9ZK3Q7M8N2P'  # torn, no newline
    file = write_raw(paths, "s1", good_line("s1", 1) + garbage + good_line("s1", 2))
    result = read_file(file)
    assert [e.event_id for e in result.events] == [
        make_event("s1", 1)["event_id"],
        make_event("s1", 2)["event_id"],
    ]
    assert result.corruption.resynced == 1 and result.corruption.bad_crc == 1


def test_bit_flip_is_counted_and_neighbours_survive(paths: RuntimePaths) -> None:
    middle = bytearray(good_line("s1", 2))
    middle[40] ^= 0x01
    file = write_raw(paths, "s1", good_line("s1", 1) + bytes(middle) + good_line("s1", 3))
    result = read_file(file)
    assert len(result.events) == 2 and result.corruption.bad_crc == 1


def test_truncated_file_is_handled_at_every_cut_point(paths: RuntimePaths) -> None:
    blob = b"".join(good_line("s1", n) for n in range(3))
    file = write_raw(paths, "s1", blob)
    for cut in range(0, len(blob) + 1, 7):
        with open(file, "wb") as handle:
            handle.write(blob[:cut])
        result = read_file(file, final=True)
        assert len(result.events) == blob[:cut].count(b"\n")
        assert result.new_offset <= cut


def test_reader_recovers_when_the_file_shrinks(paths: RuntimePaths) -> None:
    file = write_raw(paths, "s1", good_line("s1", 1) + good_line("s1", 2))
    big = read_file(file)
    with open(file, "wb") as handle:
        handle.write(good_line("s1", 9))
    again = read_file(file, big.new_offset)
    assert [e.event_id for e in again.events] == [make_event("s1", 9)["event_id"]]


def test_junk_lines_never_raise(paths: RuntimePaths) -> None:
    bad_version = encode_line(dump({**make_event("s1", 5), "schema_version": "9.9"}))
    invalid = encode_line(dump({**make_event("s1", 6), "kind": "nope"}))
    not_object = encode_line("[1,2]")
    bad_json = encode_line("{oops")
    data = (
        b"\n\n   \n"
        + b"\x00\x01\xffrandom bytes\n"
        + bad_version
        + invalid
        + not_object
        + bad_json
        + b"x" * (MAX_LINE_BYTES + 5)
        + b"\n"
        + good_line("s1", 1)
    )
    result = read_file(write_raw(paths, "s1", data), final=True)
    c = result.corruption
    assert len(result.events) == 1
    assert (c.unknown_version, c.invalid_event, c.bad_json, c.oversize) == (1, 1, 2, 1)
    assert c.bad_format >= 1


def test_missing_file_reads_empty(tmp_path: Path) -> None:
    result = read_file(tmp_path / "nope.jsonl")
    assert result.events == [] and result.new_offset == 0


def test_misplaced_events_are_rejected(paths: RuntimePaths) -> None:
    forged = good_line("victim", 1)
    write_raw(paths, "attacker", forged)
    events, corruption, _ = read_all(paths)
    assert [e.session_id for e in events] == []
    assert corruption.misplaced == 1
    filtered, _c, _f = read_all(paths, "attacker")  # a session filter also drops the forgery
    assert filtered == []


# ------------------------------------------------------------------ concurrency (real files)


def run_pool(args: list[tuple[str, str, str, int, int, int]]) -> list[int]:
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(len(args)) as pool:
        return pool.map(append_worker, args)


def test_concurrent_writers_same_file_do_not_interleave(paths: RuntimePaths) -> None:
    jobs = [(paths.root, "s1", "main", i * 1000, 120, 4 * 1024 * 1024) for i in range(6)]
    assert run_pool(jobs) == [120] * 6
    events, corruption, files = read_all(paths, "s1")
    assert files == 1
    assert corruption.total == 0 and len({e.event_id for e in events}) == 720 == len(events)


def test_concurrent_writers_with_rotation_lose_nothing(paths: RuntimePaths) -> None:
    jobs = [(paths.root, "s1", "main", i * 1000, 100, 6000) for i in range(5)]
    assert run_pool(jobs) == [100] * 5
    events, corruption, files = read_all(paths, "s1")
    assert files > 5 and corruption.total == 0
    assert len({e.event_id for e in events}) == 500 == len(events)


def test_concurrent_writers_separate_files(paths: RuntimePaths) -> None:
    jobs = [(paths.root, "s1", f"w{i}", i * 1000, 80, 4 * 1024 * 1024) for i in range(4)]
    assert run_pool(jobs) == [80] * 4
    events, corruption, files = read_all(paths, "s1")
    assert files == 4 and corruption.total == 0 and len(events) == 320
