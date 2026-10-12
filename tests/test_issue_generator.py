from tools.github_issue_export import IssueSpec, render_issue


def test_issue_markdown_render():
    md = render_issue(IssueSpec(title="P0 Verify Live Runtime"))
    assert "# P0 Verify Live Runtime" in md


def test_acceptance_checkboxes():
    assert "- [ ]" in render_issue(IssueSpec(title="Evidence Gate"))
