"""tests/test_dashboard.py — Unit tests for dashboard.py. Disk-isolated via tmp_path."""

from unittest.mock import patch

import dashboard


def test_build_html_escapes_script_breakout(tmp_path):
    """A value containing '</script>' must not terminate the data <script> tag."""
    out = tmp_path / 'dashboard.html'
    payload = {'holdings': [{'label': 'Evil</script><img src=x onerror=alert(1)>'}]}

    with patch.object(dashboard, 'OUT_FILE', out):
        dashboard.build_html(payload)

    written = out.read_text()
    assert '</script><img' not in written
    assert '\\u003c/script>' in written
