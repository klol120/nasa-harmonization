"""Monthly schedule rules (firecal_api/schedule.py); no database needed."""
from datetime import datetime, timedelta, timezone

from firecal_api.schedule import due_at, slot_after

UTC = timezone.utc
RETRY = timedelta(hours=6)
NOW = datetime(2026, 11, 15, 12, tzinfo=UTC)


def at(*a):
    return datetime(*a, tzinfo=UTC)


def test_slot_after():
    assert slot_after(at(2026, 11, 15, 12), 1, 3) == at(2026, 12, 1, 3)
    assert slot_after(at(2026, 12, 20), 1, 3) == at(2027, 1, 1, 3)   # year rollover
    assert slot_after(at(2026, 12, 1, 2), 1, 3) == at(2026, 12, 1, 3)  # later the same day
    assert slot_after(at(2026, 12, 1, 3), 1, 3) == at(2027, 1, 1, 3)   # strictly after


def test_never_ran_runs_now():
    assert due_at(None, 1, 3, RETRY, NOW) == NOW
    assert due_at({"last_ok": None, "last_attempt": None, "last_result": None}, 1, 3, RETRY, NOW) == NOW


def test_after_success_waits_for_next_month():
    s = {"last_ok": at(2026, 11, 15, 11), "last_attempt": at(2026, 11, 15, 10), "last_result": "ok"}
    assert due_at(s, 1, 3, RETRY, NOW) == at(2026, 12, 1, 3)


def test_missed_slot_runs_at_next_start():
    s = {"last_ok": at(2026, 10, 2), "last_attempt": at(2026, 10, 1, 23), "last_result": "ok"}
    assert due_at(s, 1, 3, RETRY, NOW) == at(2026, 11, 1, 3) < NOW  # overdue: runs now


def test_failure_retries_later_and_interrupted_runs_now():
    failed = {"last_ok": at(2026, 10, 2), "last_attempt": at(2026, 11, 15, 11), "last_result": "daily cap"}
    assert due_at(failed, 1, 3, RETRY, NOW) == at(2026, 11, 15, 17)
    first_failed = {"last_ok": None, "last_attempt": at(2026, 11, 15, 11), "last_result": "network"}
    assert due_at(first_failed, 1, 3, RETRY, NOW) == at(2026, 11, 15, 17)
    interrupted = {**failed, "last_result": "running"}
    assert due_at(interrupted, 1, 3, RETRY, NOW) == NOW
