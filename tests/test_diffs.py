from attest.review.diffs import parse_diff

DIFF = """\
diff --git a/pkg/mod.py b/pkg/mod.py
index 111..222 100644
--- a/pkg/mod.py
+++ b/pkg/mod.py
@@ -10,3 +10,4 @@ def f():
 context
+added line
 context
 context
@@ -40,0 +42,2 @@ def g():
+two added
+lines here
diff --git a/other.txt b/other.txt
--- a/other.txt
+++ b/other.txt
@@ -1 +1 @@
-old
+new
"""


def test_parse_hunk_ranges() -> None:
    d = parse_diff(DIFF)
    assert d.hunks["pkg/mod.py"] == [(10, 13), (42, 43)]
    assert d.hunks["other.txt"] == [(1, 1)]
    assert d.files == ["other.txt", "pkg/mod.py"]


def test_anchor_in_hunk() -> None:
    d = parse_diff(DIFF)
    assert d.anchor_in_hunk("pkg/mod.py", 11)
    assert d.anchor_in_hunk("pkg/mod.py", 42)
    assert not d.anchor_in_hunk("pkg/mod.py", 41)
    assert not d.anchor_in_hunk("pkg/mod.py", 44)
    assert not d.anchor_in_hunk("missing.py", 10)
    # path normalization: backslashes and leading ./
    assert d.anchor_in_hunk("pkg\\mod.py", 10)
    assert d.anchor_in_hunk("./pkg/mod.py", 10)


def test_zero_count_hunk_ignored() -> None:
    # pure deletion: +40,0 means no new-file lines
    text = """\
diff --git a/x.py b/x.py
--- a/x.py
+++ b/x.py
@@ -40,2 +40,0 @@
-gone
-gone
"""
    d = parse_diff(text)
    assert d.hunks == {}


def test_dot_directory_paths_survive_normalization() -> None:
    # regression: lstrip('./') strips CHARACTERS — '.github/x.yml' must not
    # become 'github/x.yml', and '.env' must not become 'env'
    text = """\
diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
--- a/.github/workflows/ci.yml
+++ b/.github/workflows/ci.yml
@@ -1,2 +1,3 @@
 name: ci
+run: echo hi
 on: push
"""
    d = parse_diff(text)
    assert d.anchor_in_hunk(".github/workflows/ci.yml", 2)
    assert d.anchor_in_hunk("./.github/workflows/ci.yml", 2)
    assert not d.anchor_in_hunk("github/workflows/ci.yml", 2)


def test_spoofed_file_header_in_hunk_content_ignored() -> None:
    # regression: an added line whose content is '++ b/evil.py' renders as
    # '+++ b/evil.py' and must not poison the hunk map
    text = """\
diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,1 +1,3 @@
 real line
+++ b/evil.py
+@@ -1,0 +1,99 @@
"""
    d = parse_diff(text)
    assert "evil.py" not in d.hunks
    assert not d.anchor_in_hunk("evil.py", 50)
    assert d.anchor_in_hunk("a.py", 2)
