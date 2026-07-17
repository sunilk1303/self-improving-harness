import json

from harness.ledger import Ledger


def test_chain_appends_and_verifies(tmp_path):
    led = Ledger(tmp_path / "ledger.jsonl")
    for i in range(5):
        led.append("test_event", {"i": i})
    ok, msg = led.verify()
    assert ok, msg
    assert "5 events" in msg


def test_tamper_detected(tmp_path):
    path = tmp_path / "ledger.jsonl"
    led = Ledger(path)
    for i in range(4):
        led.append("test_event", {"i": i})

    lines = path.read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[1])
    rec["payload"]["i"] = 999  # retroactive edit
    lines[1] = json.dumps(rec, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ok, msg = led.verify()
    assert not ok
    assert "line 2" in msg


def test_deletion_breaks_chain(tmp_path):
    path = tmp_path / "ledger.jsonl"
    led = Ledger(path)
    for i in range(4):
        led.append("test_event", {"i": i})
    lines = path.read_text(encoding="utf-8").splitlines()
    del lines[1]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, _ = led.verify()
    assert not ok
