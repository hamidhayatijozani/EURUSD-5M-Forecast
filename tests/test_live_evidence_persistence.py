from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from scripts import live_minute_loop as loop


def test_evidence_push_rebases_and_retries_after_non_fast_forward():
    pushes = 0

    def fake_run(args, **kwargs):
        nonlocal pushes
        if args[:2] == ["git", "push"]:
            pushes += 1
            if pushes == 1:
                return CompletedProcess(args, 1, "", "non-fast-forward")
        return CompletedProcess(args, 0, "", "")

    with patch.object(loop.subprocess, "run", side_effect=fake_run), patch.object(loop.time, "sleep"):
        loop._push_commit_with_rebase(max_attempts=3)

    assert pushes == 2


def test_evidence_push_fails_loudly_after_retry_budget():
    def fake_run(args, **kwargs):
        if args[:2] == ["git", "push"]:
            return CompletedProcess(args, 1, "", "non-fast-forward")
        return CompletedProcess(args, 0, "", "")

    with patch.object(loop.subprocess, "run", side_effect=fake_run), patch.object(loop.time, "sleep"):
        with pytest.raises(RuntimeError, match="LIVE_EVIDENCE_PUSH_RETRIES_EXHAUSTED"):
            loop._push_commit_with_rebase(max_attempts=2)


def test_evidence_rebase_conflict_aborts_and_fails_closed():
    def fake_run(args, **kwargs):
        if args[:2] == ["git", "rebase"] and args[2] == "origin/main":
            return CompletedProcess(args, 1, "", "content conflict")
        return CompletedProcess(args, 0, "", "")

    with patch.object(loop.subprocess, "run", side_effect=fake_run):
        with pytest.raises(RuntimeError, match="LIVE_EVIDENCE_REBASE_CONFLICT"):
            loop._push_commit_with_rebase(max_attempts=2)
