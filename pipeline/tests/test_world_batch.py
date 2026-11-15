"""World batch: what a restart does with the state file."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("world_batch", Path(__file__).resolve().parents[1] / "tools" / "world_batch.py")
wb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wb)


def test_resume_keeps_finished_work_and_retries_an_interrupted_country_once():
    state = {
        "_bootstrap": {"ok": True},
        "Spain": {"ok": True, "tries": 1},                 # done: never redone
        "Italy": {"ok": False, "tries": 1, "why": "x"},    # failed: never redone
        "France": {"ok": None, "tries": 1},                # interrupted once: gets another try
        "Brazil": {"ok": None, "tries": 2},                # interrupted twice: marked failed
    }
    assert wb.resume(state) == ["Brazil"]
    assert state["Spain"] == {"ok": True, "tries": 1} and state["Italy"]["ok"] is False
    assert state["France"] == {"ok": None, "tries": 1}
    assert state["Brazil"]["ok"] is False and "out of memory" in state["Brazil"]["why"]
    assert state["_bootstrap"] == {"ok": True}


def test_bootstrap_gives_up_after_its_tries(tmp_path, monkeypatch):
    monkeypatch.setattr(wb, "STATE", tmp_path / "state.json")
    monkeypatch.setattr(wb, "LOG", tmp_path / "log")
    monkeypatch.setattr(wb, "run", lambda args: (False, "boom"))
    state = {}
    for _ in range(wb.MAX_BOOTSTRAP_TRIES):
        assert wb.bootstrap(state) is False
    assert wb.bootstrap(state) is None and state["_bootstrap"]["tries"] == wb.MAX_BOOTSTRAP_TRIES
    monkeypatch.setattr(wb, "run", lambda args: (True, ""))
    assert wb.bootstrap({"_bootstrap": {"ok": True}}) is True
