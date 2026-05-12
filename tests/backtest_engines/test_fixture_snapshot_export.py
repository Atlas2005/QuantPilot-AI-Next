import json

from tools.manual_backtest_prototypes.export_phase3_fixture_snapshot import (
    build_fixture_snapshot,
    write_fixture_snapshot,
)


def test_build_fixture_snapshot_reads_fake_phase3_fixture() -> None:
    snapshot = build_fixture_snapshot()

    assert snapshot["source"] == "phase3_fake_local_fixture"
    assert snapshot["row_count"] == 6
    assert "symbol" in snapshot["columns"]
    assert snapshot["notes"] == "Fake local fixture only; not real market data."


def test_snapshot_output_shape_is_serializable() -> None:
    json.dumps(build_fixture_snapshot())


def test_write_fixture_snapshot_uses_temporary_path(tmp_path) -> None:
    output = tmp_path / "snapshot.json"

    written = write_fixture_snapshot(output_path=output)

    assert written == output
    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded["row_count"] == 6
    assert loaded["source"] == "phase3_fake_local_fixture"

