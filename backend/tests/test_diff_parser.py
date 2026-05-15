from __future__ import annotations

from app.utils.diff_parser import parse_patch

GITHUB_PATCH = """@@ -1,4 +1,5 @@
 def login(user):
-    q = "SELECT * FROM users"
+    q = f"SELECT * FROM users WHERE name = {user}"
+    cursor.execute(q)
     row = cursor.fetchone()
     return row"""

MULTI_HUNK = """@@ -1,2 +1,3 @@
 import os
+import sys
 import json
@@ -10,3 +11,4 @@ def handler():
     a = 1
     b = 2
+    c = 3
     return a"""


def test_single_hunk_line_numbers():
    hunks = parse_patch("auth.py", GITHUB_PATCH)
    assert len(hunks) == 1
    hunk = hunks[0]
    assert hunk.new_start == 1
    assert hunk.new_end == 5
    added = hunk.added_lines
    assert [line.new_lineno for line in added] == [2, 3]
    assert "f\"SELECT" in added[0].content
    assert all(line.kind in {"added", "context"} for line in hunk.lines)


def test_multi_hunk():
    hunks = parse_patch("app.py", MULTI_HUNK)
    assert len(hunks) == 2
    assert hunks[0].new_start == 1
    assert hunks[1].new_start == 11
    assert [line.new_lineno for line in hunks[0].added_lines] == [2]
    assert [line.new_lineno for line in hunks[1].added_lines] == [13]


def test_empty_patch_returns_no_hunks():
    assert parse_patch("x.py", "") == []
    assert parse_patch("x.py", "   ") == []


def test_malformed_patch_returns_no_hunks():
    assert parse_patch("x.py", "not a real diff at all") == []
