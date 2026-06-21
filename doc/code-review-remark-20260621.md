# Code Review Remarks — git-lsvtree-ui

**Date:** 2026-06-21  
**Scope:** All 18 source files (core, layout, ui, app)  
**Verdict:** WARNING — 5 Major, 0 Critical, 19 Notes

---

## core/git_repo.py

| Severity | Line | Issue |
|----------|------|-------|
| Note | 94–99 | `current_branch()` returns hardcoded `"main"` on detached HEAD or any non-`main` default branch. Downstream `BranchRebuilder` uses this as the main timeline seed, so `master` / `trunk` / `develop` repos are mislabelled throughout the UI. |
| Note | 80–92 | `git()` never raises on non-zero exit; callers must remember to use `git_checked()`. Asymmetric API is a latent misuse trap. |

---

## core/history_loader.py

| Severity | Line | Issue |
|----------|------|-------|
| **Major** | 53, 70 | `git log` format uses `\x01` (record separator) and `\x02` (field separator). A commit body containing a literal `\x01` byte corrupts the `raw.split(US)` split, silently misattributing fields or dropping commits. Fix: use a multi-character sentinel that cannot appear in git output (e.g., `\x00RECORD\x00`). |
| Note | 187 | `all_tags[:50]` hard-caps repo-wide tag annotation at 50 with no warning when the cap is hit. |
| Note | 109 | `int(author_time or 0)` silently swallows malformed timestamps as epoch 0 with no log warning. |

---

## core/graph_model.py

| Severity | Line | Issue |
|----------|------|-------|
| Note | 74–76 | `__post_init__` wraps `nodes`/`branches` in `MappingProxyType` via `object.__setattr__`. Any future `dataclasses.replace()` on a `GraphModel` bypasses `__post_init__`, leaving a plain `dict`. Correct today but fragile. |

---

## core/branch_rebuilder.py

| Severity | Line | Issue |
|----------|------|-------|
| **Major** | 77 | `nodes[edge.src]` and `nodes[edge.dst]` accessed without existence check. Any gap in `assign_chain` coverage raises `KeyError` with no diagnostic. |
| Note | 37 | Merge commits not matching `parse_merge_source` patterns always get `branch@<hash>`, preventing deduplication across reloads. Intentional but silent. |

---

## core/key_selector.py

| Severity | Line | Issue |
|----------|------|-------|
| Note | 30–33 | `threshold <= 0` guard is misplaced: fires after the early-returns, so threshold=0 on an empty graph bypasses it. |
| Note | 167–176 | `_nearest_visible_main_ancestor` is O(n) per node → O(n²) total for linear graphs. Bounded by threshold but worth noting. |

---

## core/collapse_model.py

| Severity | Line | Issue |
|----------|------|-------|
| Note | 18 | `expanded_runs = expanded_runs or set()` converts `frozenset \| None` to a plain `set`, inconsistent with the `frozenset` annotation. |

---

## core/diff_service.py

| Severity | Line | Issue |
|----------|------|-------|
| Note | 38–39 | `git show <hash>:<path>` on binary files is decoded as UTF-8 with `errors="replace"`. No guard or early-exit for binary content; diff panel shows garbled output. |

---

## core/project_tree.py

| Severity | Line | Issue |
|----------|------|-------|
| Note | 77 | `_normalize_tracked_path` path-traversal defense via `normpath` + `startswith("../")` is correct but non-obvious. |

---

## layout/geometry.py

No issues.

---

## layout/tree_layout.py

| Severity | Line | Issue |
|----------|------|-------|
| **Major** | 597–598 | `_swap_optimize_columns`: O(N² × M²) per pass. The `_crossing_count` call at line 597 re-computes a value already known from the previous iteration. Fix: cache current crossing count, update only on accepted swaps. |
| Note | 421–426 | `legal_candidates` scan has no upper bound. On a dense 200-column graph, unbounded linear scan per branch assignment. |

---

## ui/items.py

| Severity | Line | Issue |
|----------|------|-------|
| Note | 47–48 | Throwaway `QGraphicsSimpleTextItem` created just to measure badge text width. For many tagged nodes, use `QFontMetrics` instead. |

---

## ui/graph_scene.py

| Severity | Line | Issue |
|----------|------|-------|
| Note | 173–177 | `_update_edge_info_item` accesses `self._layout.nodes[src_id]` without existence check. Edge-click during layout-reload race could raise `KeyError`. |

---

## ui/graph_view.py

| Severity | Line | Issue |
|----------|------|-------|
| Note | 50–51 | `self._pan_start` set in `mousePressEvent` but never initialized in `__init__`. Synthetic middle-button-move events before a press raise `AttributeError`. Fix: initialize to `QPoint()` in `__init__`. |

---

## ui/diff_panel.py

| Severity | Line | Issue |
|----------|------|-------|
| Note | 263–269 | `show_error` passes raw exception message (including internal paths from `GitCommandError` stderr) directly to UI. Acceptable for local tool. |

---

## ui/detail_panel.py

| Severity | Line | Issue |
|----------|------|-------|
| Note | 30 | `datetime.fromtimestamp(author_time)` uses local timezone. A silently-defaulted `author_time=0` displays as `1970-01-01 <offset>` with no indication the timestamp was missing. |
| Note | 43–76 | All user-controlled fields pass through `html.escape()`. No XSS surface. Clean. |

---

## ui/project_navigator.py

No actionable issues.

---

## app/graph_loader.py

| Severity | Line | Issue |
|----------|------|-------|
| **Major** | 26–35 | `_POPEN_FLAGS` and `_GIT_ENV` duplicated verbatim from `core/git_repo.py`. `ProjectLoaderWorker` bypasses `GitRepo` and calls `subprocess.run` directly. Any future change to git environment setup in the core layer silently won't apply to project scanning. Fix: expose `GitRepo.run_git_at(path, *args)` static helper and use from both call sites. |
| Note | 127 | `if not str(repo_root):` is always `False`; `str(Path(...))` is never empty. Dead guard. |
| Note | 198–204 | `logger.exception` used for all failures including expected `ValueError` ("no git history"). Use `logger.warning` for known error paths; reserve `logger.exception` for unexpected exceptions. |

---

## app/main_window.py

| Severity | Line | Issue |
|----------|------|-------|
| **Major** | 319–322 | `reload_current_file` defaults `mode="key"` unconditionally. Pressing F5 in Full mode silently downgrades to Key mode. Fix: `mode = mode or self.current_mode`. |
| Note | 302–317 | `include_repo_tags=True` unconditional. For repos with 50+ tags, every load fires 50 sequential `git rev-list` subprocess calls with no UI option to disable. |
| Note | 407 | `scene.render(painter)` for PNG export uses native resolution with no DPI scaling. Output appears lower resolution on HiDPI displays. |
| Note | 448 | `self.detail_panel.setPlainText(...)` calls inherited `QTextEdit` method directly, bypassing `DetailPanel`'s own API. Fragile if `DetailPanel` is refactored. |

---

## Summary — Top 5 Most Important Issues

### 1. Record splitter corruption — `core/history_loader.py:53,70` [Major]

`git log` format uses `\x01` / `\x02` as delimiters — same bytes as `US`/`GS`. A commit body containing a literal `\x01` byte silently corrupts field parsing, misattributing data or dropping commits. No error is raised. Fix: use a multi-character sentinel (`\x00RECORD\x00` / `\x00FIELD\x00`) or switch to NUL-delimited `git log -z`.

### 2. Duplicated subprocess environment — `app/graph_loader.py:26-35` [Major]

`_POPEN_FLAGS` and `_GIT_ENV` copied from `core/git_repo.py`. `ProjectLoaderWorker` bypasses `GitRepo` entirely. Future changes to git environment config (proxy, timeout, credential suppression) in `git_repo.py` silently won't apply to project scanning. Fix: `GitRepo.run_git_at(path, *args)` static helper shared by both call sites.

### 3. Quadratic crossing optimizer — `layout/tree_layout.py:597-598` [Major]

`_swap_optimize_columns` is O(N² × M²) per pass: calls `_crossing_count` (O(M²)) twice per pair in an O(N²) loop. The `before` variable at line 597 re-computes a value already known. Fix: cache crossing count, update only on accepted swaps.

### 4. Wrong default branch name — `core/git_repo.py:94-99` [Major → Note]

`current_branch()` returns hardcoded `"main"` on detached HEAD. On repos with `master` / `trunk` / `develop` as default, the entire main timeline is mislabelled throughout the UI. Fix: `git symbolic-ref --short HEAD`, fall back to `git config init.defaultBranch`.

### 5. F5 Reload silently downgrades to Key mode — `app/main_window.py:319-322` [Major]

`reload_current_file(mode="key")` is the default. User in Full mode pressing F5 silently drops to Key mode. Fix: one line — `mode = mode or self.current_mode`.

---

## Issue Counts

| Severity | Count |
|----------|-------|
| Critical | 0 |
| Major    | 5 |
| Note     | 19 |
