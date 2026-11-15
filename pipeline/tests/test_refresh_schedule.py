"""Monthly schedule rules of the container runner (tools/refresh.py)."""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import refresh  # noqa: E402

UTC = dt.timezone.utc
RETRY = dt.timedelta(hours=6)
NOW = dt.datetime(2026, 11, 15, 12, tzinfo=UTC)


def iso(*a):
    return dt.datetime(*a, tzinfo=UTC).isoformat()


def test_never_ran_runs_now():
    assert refresh.due_at({}, 1, 3, RETRY, NOW) == NOW


def test_after_success_waits_for_next_month():
    s = {"last_ok": iso(2026, 11, 15, 11), "last_attempt": iso(2026, 11, 15, 10), "last_result": "ok"}
    assert refresh.due_at(s, 1, 3, RETRY, NOW) == dt.datetime(2026, 12, 1, 3, tzinfo=UTC)
    s = {"last_ok": iso(2026, 12, 20), "last_attempt": iso(2026, 12, 19), "last_result": "ok"}
    assert refresh.due_at(s, 1, 3, RETRY, NOW) == dt.datetime(2027, 1, 1, 3, tzinfo=UTC)


def test_failure_retries_later_and_interrupted_runs_now():
    failed = {"last_ok": iso(2026, 10, 2), "last_attempt": iso(2026, 11, 15, 11), "last_result": "download failed"}
    assert refresh.due_at(failed, 1, 3, RETRY, NOW) == dt.datetime(2026, 11, 15, 17, tzinfo=UTC)
    assert refresh.due_at({**failed, "last_result": "running"}, 1, 3, RETRY, NOW) == NOW
