"""Render a GitHub issue body without making network calls."""
from dataclasses import dataclass, field


@dataclass
class IssueSpec:
    title: str
    problem: str = "The end-to-end evidence chain is not yet proven on a post-change live forecast."
    acceptance: list[str] = field(default_factory=lambda: [
        "Strict feature_cutoff_at < issued_at < target_ts contract passes.",
        "A new prediction persists decision_snapshot, snapshot_sha256, and evidence_hash.",
        "The same prediction is present in SQLite and append-only JSONL.",
        "Tampering is detected by the audit command.",
        "Settlement is rejected before target_ts and accepted once after target_ts.",
        "A post-change live prediction is settled and its audit result is attached.",
    ])


def render_issue(issue: IssueSpec) -> str:
    checks = "\n".join(f"- [ ] {item}" for item in issue.acceptance)
    return f"# {issue.title}\n\n## Problem\n{issue.problem}\n\n## Acceptance criteria\n{checks}\n"
