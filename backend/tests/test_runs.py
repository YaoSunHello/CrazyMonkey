"""Runs must not overwrite each other, and must be findable afterwards.

The bug these guard against is silent: a single fixed output path means every
run destroys the one before it, and you only notice when you go looking for a
run that is already gone.
"""

from __future__ import annotations

import json

import pytest

from app import runs as runs_module
from app.runs import RunDir, list_runs, new_run_id, resolve


@pytest.fixture(autouse=True)
def isolated_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(runs_module, "OUTPUTS", tmp_path)
    monkeypatch.setattr(runs_module, "RUNS", tmp_path / "runs")


def make(account: str, run_id: str, **summary) -> RunDir:
    run = RunDir(run_id)
    run.write_summary({"account": account, **summary})
    run.trace_path.write_text('{"kind":"state","label":"starting"}\n', encoding="utf-8")
    return run


def test_two_runs_of_the_same_account_do_not_collide():
    make("GBP_3252", "20260905-100000-GBP_3252", rows=16, accepted=True)
    make("GBP_3252", "20260905-110000-GBP_3252", rows=16, accepted=False)

    records = list_runs()
    assert len(records) == 2
    assert {r.run_id for r in records} == {
        "20260905-100000-GBP_3252",
        "20260905-110000-GBP_3252",
    }


def test_runs_are_listed_newest_first():
    make("A", "20260905-100000-A")
    make("B", "20260905-120000-B")
    assert [r.account for r in list_runs()] == ["B", "A"]


def test_resolve_by_prefix():
    make("USD_4373", "20260905-133000-USD_4373", rows=19)
    assert resolve("20260905-1330").account == "USD_4373"
    assert resolve("USD_4373").rows == 19


def test_resolve_falls_back_to_the_marked_latest():
    make("A", "20260905-100000-A")
    newest = make("B", "20260905-090000-B")   # earlier id, but marked latest
    newest.mark_latest()
    assert resolve(None).account == "B"


def test_resolve_returns_none_when_nothing_matches():
    make("A", "20260905-100000-A")
    assert resolve("nope") is None


def test_a_batch_groups_its_documents_under_one_stamp():
    """Documents run together share a prefix, so a batch reads as a unit."""
    batch = "20260905-140000"
    ids = [new_run_id(account, batch=batch) for account in ("GBP_3252", "USD_4373")]
    assert ids == [f"{batch}-GBP_3252", f"{batch}-USD_4373"]
    assert len({i.rsplit("-", 1)[0] for i in ids}) == 1


def test_every_attempt_is_kept_not_just_the_last():
    run = make("A", "20260905-100000-A")
    run.write_attempt(1, "print('first try')")
    run.write_attempt(2, "print('second try')")
    assert (run.path / "attempt-1.py").read_text(encoding="utf-8") == "print('first try')"
    assert (run.path / "attempt-2.py").read_text(encoding="utf-8") == "print('second try')"


def test_rows_are_written_with_the_checks_that_judged_them():
    run = make("A", "20260905-100000-A")
    run.write_rows({"account": "A", "rows": [{"balance": "1.00"}], "checks": [{"name": "x"}]})
    payload = json.loads((run.path / "rows.json").read_text(encoding="utf-8"))
    assert payload["rows"][0]["balance"] == "1.00"
    assert payload["checks"][0]["name"] == "x"
