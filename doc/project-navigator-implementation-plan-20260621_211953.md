# Project Navigator Implementation Plan

Timestamp: 2026-06-21 21:19:53 Asia/Shanghai

## Scope

[KNOWN] This plan implements Phase 10 from `doc/design.md`: opening a Git project directory and browsing tracked files through a dockable project navigator.

[KNOWN] The version tree canvas remains single-file. Selecting a file from the navigator reuses the existing single-file graph loading pipeline.

[KNOWN] This plan does not implement multi-file history visualization, checkout, merge, write actions, or untracked-file browsing.

## User Requirement

[KNOWN] Add a directory navigation bar on the right side of the version tree display area.

[KNOWN] The application should open a whole project and initially show the project's first-level directory entries.

[KNOWN] Directories use `+` / `-` indicators for expand/collapse.

[KNOWN] The navigation bar can be hidden and floated to reduce long-term occupation of the version tree display area.

## Architecture Decision

[INFERRED] The safest design is a project-navigation layer above the existing file-history pipeline:

```text
Open Project
  -> load tracked file tree
  -> show ProjectNavigatorDock
  -> user selects one file
  -> existing GraphLoaderWorker loads that file
  -> GraphScene renders that file's version tree
```

[INFERRED] This minimizes regression risk because `HistoryLoader`, `BranchRebuilder`, `KeySelector`, `CollapseModel`, and `TreeLayout` continue to operate on one file at a time.

## Implementation Phases

### Phase 10.0 — Documentation Baseline

Status: completed in design document.

Goal:

[KNOWN] Keep implementation aligned with `doc/design.md` v1.6.

Deliverables:

- [KNOWN] `doc/design.md` has Phase 10 project navigator architecture.
- [KNOWN] This implementation plan defines test order and implementation steps.

### Phase 10.1 — Core Project Tree Model

Status: completed.

Goal:

[KNOWN] Add a pure-Python project tree model and builder with no Qt dependency.

Files:

- `core/project_tree.py`
- `tests/test_project_tree.py`

Interfaces:

```python
@dataclass(frozen=True)
class ProjectTreeNode:
    name: str
    rel_path: str
    kind: Literal["directory", "file"]
    children: tuple["ProjectTreeNode", ...] = ()
    tracked: bool = False

@dataclass(frozen=True)
class ProjectTree:
    repo_root: Path
    root: ProjectTreeNode
    tracked_file_count: int

class ProjectTreeBuilder:
    def build(repo_root: Path, tracked_paths: Iterable[str]) -> ProjectTree: ...
```

TDD tests first:

- `test_project_tree_builds_flat_files`
- `test_project_tree_builds_nested_directories`
- `test_project_tree_sorts_directories_before_files`
- `test_project_tree_rejects_empty_tracked_paths`
- `test_project_tree_normalizes_posix_paths`

Acceptance criteria:

- [KNOWN] Pure unit tests pass without Qt.
- [KNOWN] Sorting is deterministic: directories first, files second, then case-insensitive name.
- [KNOWN] Empty path segments and duplicate tracked paths are handled deterministically.

Estimated code size:

[INFERRED] 100-160 LOC implementation, 80-130 LOC tests.

Completion notes:

- [KNOWN] Added `core/project_tree.py`.
- [KNOWN] Added `tests/test_project_tree.py`.
- [COMPUTED] Target test result: `5 passed`.
- [COMPUTED] Full regression result after Phase 10.1: `131 passed`.
- [COMPUTED] `compileall` passed.

### Phase 10.2 — Project Loader Worker

Status: completed.

Goal:

[KNOWN] Load a Git project tree in a background worker.

Files:

- `app/graph_loader.py`
- `tests/test_app_phase1.py` or new `tests/test_project_loader.py`

Interfaces:

```python
@dataclass(frozen=True)
class ProjectLoadRequest:
    project_path: Path

@dataclass(frozen=True)
class ProjectLoadResult:
    repo_root: Path
    tree: ProjectTree

class ProjectLoaderWorker(QRunnable):
    signals.loaded: Signal(object)
    signals.failed: Signal(str)
```

Git commands:

```bash
git -C <project_path> rev-parse --show-toplevel
git -C <repo_root> ls-files -z
```

TDD tests first:

- `test_project_loader_resolves_repo_root`
- `test_project_loader_builds_tree_from_git_ls_files`
- `test_project_loader_fails_for_non_git_directory`
- `test_project_loader_fails_for_empty_tracked_file_list`

Acceptance criteria:

- [KNOWN] Worker returns `ProjectLoadResult` with repo root and tree.
- [KNOWN] Worker emits failure message without raising to Qt event loop.
- [KNOWN] Existing `GraphLoaderWorker` behavior is unchanged.

Estimated code size:

[INFERRED] 90-140 LOC implementation, 80-140 LOC tests.

Completion notes:

- [KNOWN] Added `ProjectLoadRequest`, `ProjectLoadResult`, and `ProjectLoaderWorker` in `app/graph_loader.py`.
- [KNOWN] Added `tests/test_project_loader.py`.
- [COMPUTED] Target test result: `4 passed`.
- [COMPUTED] Phase 10.1 + 10.2 tests: `9 passed`.
- [COMPUTED] Full regression result after Phase 10.2: `135 passed`.
- [COMPUTED] `compileall` passed.

### Phase 10.3 — Project Navigator UI

Status: completed.

Goal:

[KNOWN] Add a dockable project tree widget with explicit `+` / `-` directory expand/collapse and file selection.

Files:

- `ui/project_navigator.py`
- `tests/test_project_navigator.py` or app-level Qt tests

Recommended UI:

[INFERRED] Use `QTreeWidget` inside a `QWidget`, hosted by `QDockWidget` in `MainWindow`.

Rationale:

[COMMON] `QTreeWidget` already supports tree expansion, selection, keyboard navigation, and row painting. Explicit `+` / `-` can be represented in the first column text or through custom item text.

Interfaces:

```python
class ProjectNavigator(QWidget):
    fileSelected = Signal(Path)
    def set_project_tree(self, tree: ProjectTree) -> None: ...
    def set_selected_file(self, rel_path: str | None) -> None: ...
    def expanded_dirs(self) -> set[str]: ...
    def restore_expanded_dirs(self, dirs: set[str]) -> None: ...
```

Visual format:

```text
+ src
- tests
    test_app.py
  README.md
```

TDD tests first:

- `test_project_navigator_populates_first_level_items`
- `test_project_navigator_expands_and_collapses_directory`
- `test_project_navigator_emits_file_selected`
- `test_project_navigator_preserves_expanded_dirs`
- `test_project_navigator_marks_selected_file`

Acceptance criteria:

- [KNOWN] First-level entries show immediately.
- [KNOWN] Directory expansion does not trigger file graph loading.
- [KNOWN] File click emits absolute file path.
- [KNOWN] Hide/show does not destroy navigator state.

Estimated code size:

[INFERRED] 160-260 LOC implementation, 120-220 LOC tests.

Completion notes:

- [KNOWN] Added `ui/project_navigator.py`.
- [KNOWN] Added `tests/test_project_navigator.py`.
- [COMPUTED] Target test result: `5 passed`.
- [COMPUTED] Phase 10.1 + 10.2 + 10.3 tests: `14 passed`.
- [COMPUTED] Full regression result after Phase 10.3: `140 passed`.
- [COMPUTED] `compileall` passed.

### Phase 10.4 — MainWindow Integration

Status: not started.

Goal:

[KNOWN] Wire project opening, navigator dock visibility, and file selection into existing app state.

Files:

- `app/main_window.py`
- `ui/status_bar.py` if status display needs project root
- `tests/test_app_phase1.py`

New actions:

```text
File -> Open Project...
View -> Project Navigator
```

State additions:

```python
current_project_root: Path | None
current_project_tree: ProjectTree | None
expanded_project_dirs: set[str]
selected_project_file: str | None
```

Workflow:

```text
open_project_dialog()
  -> directory chooser
  -> ProjectLoaderWorker
  -> _on_project_loaded(result)
  -> project navigator dock visible

ProjectNavigator.fileSelected(path)
  -> load_file(path)
  -> existing GraphLoaderWorker
```

TDD tests first:

- `test_main_window_open_project_starts_project_loader`
- `test_main_window_project_loaded_shows_navigator`
- `test_main_window_project_file_selection_starts_graph_loader`
- `test_main_window_project_load_failure_keeps_current_graph`
- `test_main_window_toggle_project_navigator_visibility_preserves_tree`

Acceptance criteria:

- [KNOWN] Opening a project does not clear the current graph until a file is selected.
- [KNOWN] Selecting a file clears old node/edge selection state through existing graph reload path.
- [KNOWN] Navigator can be hidden and shown again.
- [KNOWN] Single-file `Open` still works as before.

Estimated code size:

[INFERRED] 140-230 LOC implementation, 100-180 LOC tests.

### Phase 10.5 — README and UX Documentation

Status: not started.

Goal:

[KNOWN] Document project mode usage after implementation.

Files:

- `README.md`
- `doc/design.md` if implementation deviates from design

README additions:

- `Open Project...` usage.
- Navigator `+` / `-` behavior.
- File selection loads version tree.
- Navigator hide/show/floating behavior.

TDD:

[INFERRED] No automated test needed for README-only text unless project has doc linting.

Estimated code size:

[INFERRED] 20-50 README lines.

### Phase 10.6 — Regression and Manual Validation

Status: not started.

Automated validation:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPYCACHEPREFIX=/private/tmp/git_lsvtree_ui_pycache python -m pytest tests -q -p no:cacheprovider
PYTHONPYCACHEPREFIX=/private/tmp/git_lsvtree_ui_pycache python -m compileall -q .
```

Manual validation:

1. Open app.
2. Open a project directory.
3. Verify right-side navigator appears with first-level tracked entries.
4. Expand a directory using `+`.
5. Collapse it using `-`.
6. Select a tracked file and verify the version tree loads.
7. Hide navigator and verify graph canvas remains usable.
8. Show navigator again and verify expansion/selection state remains.
9. Float navigator and verify selecting another file still loads correctly.
10. Verify existing single-file Open still works.

## Risk Assessment

### Risk 1 — Large repository UI freeze

[INFERRED] Building the tree from many tracked files can be expensive if done on the UI thread.

Mitigation:

[KNOWN] Project scanning must run in `ProjectLoaderWorker`.

### Risk 2 — Navigator consumes graph width

[INFERRED] A right dock can reduce visible graph width when docked.

Mitigation:

[KNOWN] Dock must be closable/floating and restorable from View menu.

### Risk 3 — Mixing project state with file graph state

[INFERRED] If project state and graph state are coupled, file load failures can clear the navigator.

Mitigation:

[KNOWN] Keep `current_project_tree` separate from `current_graph/current_layout`.

### Risk 4 — Showing too many files initially

[INFERRED] Rendering all nodes expanded can be slow and visually noisy.

Mitigation:

[KNOWN] Initial view only shows first-level nodes; directories expand on demand in the widget.

## Definition of Done

- [KNOWN] Design and implementation plan exist before code.
- [KNOWN] TDD tests are added before implementation for each phase.
- [KNOWN] Existing single-file flow still passes tests.
- [KNOWN] Project mode can open a repo, browse tracked files, and load selected file histories.
- [KNOWN] Navigator dock can be hidden, shown, floated, and preserves state.
- [KNOWN] Full regression test suite and compile check pass.
