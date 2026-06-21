# git-lsvtree-ui Design Document

**Version:** 1.6  
**Date:** 2026-06-21  
**Status:** Design updated for Phase 10 project directory navigation

---

## 1. Background and Goals

`git-lsvtree-ui` evolves the static SVG-generating `git-lsvtree` script into an interactive desktop version-tree browser, modeled on ClearCase's **Version Tree Browser**.

The static SVG approach is suitable for archiving and overall layout inspection, but does not support interactive operations such as version detail viewing, version selection, diff, collapse/expand, zoom, and pan.

### Core goals

1. Display a single file's Git version tree in a GUI window with a toolbar.
2. Click any version node to view its details: hash, branch, tags, author, committer, dates, subject, description, parents.
3. Select any two version nodes and run a diff between them.
4. Expand and re-collapse linear-chain collapsed "run" nodes.
5. Zoom and pan the canvas freely.
6. Preserve existing full / key / collapse semantics, with the interactive UI as the primary interface.
7. Visual style aligned with ClearCase Version Tree Browser: branch column headers (blue rectangles), version nodes (blue circles), main edges (dark lines), merge edges (red dashed lines).
8. Status bar showing file, mode, version count, branch count, zoom, warnings.
9. Click any rendered edge to highlight that edge and show both endpoint versions inside the version tree area; selecting another edge replaces the previous edge info.
10. Route overlapping merge edges as separated curves where needed, and avoid drawing edges through unrelated version-node circles whenever practical.
11. Open a whole Git project directory and browse its first-level directory tree in a dockable, hideable project navigator. Selecting a tracked file from the navigator loads that file's version tree in the main canvas.

### Out of scope (v1)

- Write operations (checkout, label, merge).
- True per-file ClearCase branch semantics (Git does not record them).
- Web or browser frontend.
- Multi-file simultaneous comparison. Project navigation selects one file at a time; the version tree canvas still renders a single file history.

---

## 2. Architecture

### 2.1 Layer overview

```
git_lsvtree_ui/
├── core/          # Pure Python — no Qt dependency
├── layout/        # Pure Python — coordinate computation only
├── ui/            # Qt widgets
├── app/           # Application wiring and background workers
└── __main__.py    # Entry point
```

The strict layer rule: **core ← layout ← ui ← app**. No layer may import from a layer above it. This allows `core/` and `layout/` to be unit-tested without a Qt installation.

### 2.2 Module map

```
core/
  git_repo.py        GitRepo dataclass — wraps subprocess git calls
  project_tree.py    Project directory scanner and tracked-file tree model
  history_loader.py  Parses `git log --follow --all` into a raw GraphModel
  graph_model.py     Frozen dataclasses: VersionNode, Edge, GraphModel,
                       DisplayNode, DisplayEdge, DisplayGraph
  branch_rebuilder.py  Reconstructs branch names from first-parent topology
  key_selector.py    Selects structural skeleton + tag + sampled nodes (Key mode)
  collapse_model.py  Folds linear chains → DisplayGraph with run nodes
  diff_service.py    Fetches full file content + unified diff → DiffResult

layout/
  geometry.py        Point, Rect value types (frozen dataclasses)
  tree_layout.py     Maps DisplayGraph → LayoutGraph (pixel coordinates)
                       Output: LayoutNode, LayoutEdge, BranchHeader, LayoutGraph

ui/
  items.py           QGraphicsItem subclasses:
                       VersionNodeItem, CollapsedRunItem, EdgeItem, BranchHeaderItem
  graph_scene.py     QGraphicsScene: hit-testing, selection state, LOD, highlight
  graph_view.py      QGraphicsView: zoom, middle-button pan, wheel scroll
  project_navigator.py  Dockable project directory tree with expand/collapse and file selection
  detail_panel.py    QTextEdit: commit metadata on node click
  diff_panel.py      QWidget: side-by-side diff view with overview ruler
  status_bar.py      QStatusBar: file info, mode, zoom, warnings

app/
  graph_loader.py    QRunnable workers: GraphLoaderWorker, DiffLoaderWorker
                       Dataclasses: GraphLoadRequest, GraphLoadResult, DiffLoadRequest,
                       ProjectLoadRequest, ProjectLoadResult
  main_window.py     QMainWindow: state machine, action wiring, signal routing
  __main__.py        Entry point — QApplication + optional CLI file argument
```

### 2.3 Data flow

```
Project path / File path
  ├─► ProjectTreeLoader.load(project_root)  →  ProjectTree  (right dock navigator)
  │     └─► user selects tracked file
  └─► GitRepo.from_file()
        │  (resolves repo root, computes rel_path)
        ▼
      HistoryLoader.load()              →  GraphModel  (raw commits, parents, tags)
        ▼
      BranchRebuilder.rebuild()         →  GraphModel  (reconstructed_branch assigned)
        ▼
      KeySelector.select(mode, threshold) →  GraphModel  (pruned to N key nodes)
        ▼
      CollapseModel.build(expanded_runs)  →  DisplayGraph  (runs collapsed)
        ▼
      TreeLayout.layout(branch_order)     →  LayoutGraph   (pixel coordinates)
        ▼
      GraphScene.set_layout_graph()       →  QGraphicsItems on screen
```

All git I/O and graph computation runs in **QThreadPool workers**. The main thread only receives completed `GraphLoadResult` / `DiffResult` objects via Qt signals, so the UI stays responsive.

Project directory scanning also runs in a worker. The main thread only receives a compact project tree model and renders it in the project navigator dock.

---

## 3. Core Layer Design

### 3.1 GitRepo

Encapsulates repository root, target file relative path, and subprocess git invocations.

```python
@dataclass(frozen=True)
class GitRepo:
    repo_root: Path
    file_path: Path
    rel_path: str

    @classmethod
    def from_file(cls, file_path: Path) -> "GitRepo": ...
    def git(self, *args: str) -> CompletedProcess: ...
    def git_checked(self, *args: str) -> str: ...  # raises GitCommandError on non-zero exit
```

All git commands receive `cwd=repo_root`. File paths passed to git use the posix-formatted relative path from repo root.

### 3.1b ProjectTree

Project mode opens a Git repository root or any directory inside a Git repository. The project tree model is a lightweight file/navigation model; it does not load file histories until the user selects a concrete file.

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
```

Loading rules:

1. Resolve the project root using Git, not by trusting the selected directory:

   ```bash
   git -C <selected-dir> rev-parse --show-toplevel
   ```

2. List tracked files with:

   ```bash
   git -C <repo-root> ls-files -z
   ```

3. Build a directory tree from tracked file paths only. Ignored/untracked files are not shown in Phase 10.
4. The first render shows only the project root and first-level directory/file nodes. Child directories are lazy-expanded when the user clicks `+`.
5. Directory nodes show `+` when collapsed and `-` when expanded. File nodes have no expander.
6. Selecting a file emits the absolute file path and reuses the existing single-file graph loading pipeline.

The project tree is independent of `GraphModel`; it is navigation state, not version-history state.

### 3.2 HistoryLoader

Batch-reads single-file history using:

```bash
git log [--all] --topo-order --full-history --simplify-merges --parents \
  --format='%x01%H %P%x02%D%x02%an%x02%ae%x02%at%x02%ct%x02%s' -- <file>
```

Invisible separator characters (`\x01`, `\x02`) prevent subject text from breaking field parsing. Full commit message is not loaded up front; it is fetched on demand via `git show -s --format=%B <hash>` when the user clicks a node.

Tag loading has two paths:

1. Decorations from the primary `git log` output are always parsed. These tags are attached to commits that directly appear in the file history.
2. Repo-wide tag annotation is opt-in at the core layer through `HistoryLoader(..., include_repo_tags=True)`. The application enables this for normal UI loads so release tags that land on merge/release commits are projected to the nearest file-history anchor commit. This keeps the lower-level loader cheap by default while preserving important tag visibility in the GUI.

### 3.3 GraphModel

Core immutable data structures (all `frozen=True`):

```python
@dataclass(frozen=True)
class VersionNode:
    hash: str
    parents: tuple[str, ...]
    main_parent: str | None
    merge_parents: tuple[MergeParent, ...]
    tags: tuple[str, ...]
    author_name: str
    author_email: str
    author_time: int        # Unix timestamp
    commit_time: int
    subject: str
    topo_rank: int          # global topological order (0 = oldest)
    reconstructed_branch: str = ""
    per_branch_index: int = -1
    is_head_file_version: bool = False

@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    kind: Literal["main", "branch", "merge"]
    label: str = ""         # e.g. "merge from feature-x"

@dataclass(frozen=True)
class GraphModel:
    nodes: Mapping[str, VersionNode]   # MappingProxyType (immutable)
    edges: tuple[Edge, ...]
    order_newest_first: tuple[str, ...]
    order_oldest_first: tuple[str, ...]
    branches: Mapping[str, BranchInfo] # insertion order = column order
```

`Edge.label` is a first-class field. Earlier versions that reconstructed merge labels after key/collapse filtering lost this information; the current design preserves it on every edge.

### 3.4 BranchRebuilder

Reconstructs branch membership using a first-parent heuristic:

1. The node with the lowest topo_rank (oldest) seeds the main branch.
2. The first-parent chain from each node is followed; nodes not yet assigned get the current branch.
3. Merge commit messages (`Merge branch 'X'`) provide candidate branch names for the merge-parent chain.
4. Each branch gets a `column_hint` (main = 0, others in encounter order) for stable column layout.

All branch names are reconstructed approximations. Git does not record per-file branch affiliation.

### 3.5 KeySelector

Reduces a large graph to a manageable node set for Key mode:

**Phase 1 — Structural skeleton (always kept):**
- Branch tips and bases (first/last node of each `BranchInfo.nodes`)
- Merge sources and targets
- Branch points (out-degree > 1) and join points (in-degree > 1)
- HEAD file version

**Phase 2 — Fill budget:**
- Tag nodes (in topo order, up to remaining budget)
- Uniformly sampled plain nodes

If the skeleton alone exceeds `threshold`, the status bar shows a truncation warning.

Edges between visible nodes are rewired: for each kept node, walk `main_parent` links until a kept ancestor is found; reconstruct a direct edge with the appropriate kind (`main` or `branch`). Merge edges are similarly reconnected through the nearest visible ancestor.

### 3.6 CollapseModel

Folds linear chains into collapsed "run" nodes.

**Collapsible node criteria** (all must hold):
- `indeg == 1` and `outdeg == 1` (counting only `main` and `branch` edges, not merge edges)
- No tags
- `reconstructed_branch` is set (avoids collapsing nodes without branch assignment)

Collapsible nodes within the same branch are grouped into runs. Each run becomes a single `DisplayNode` with `kind="run"` and `source_hashes` listing all original commits.

`expanded_runs: frozenset[str]` is passed as a parameter to `build()` and is never stored inside `CollapseModel` itself — UI state stays in the application layer.

### 3.7 DiffService

```python
@dataclass(frozen=True)
class DiffResult:
    old_hash: str
    new_hash: str
    rel_path: str
    text: str          # unified diff text (kept for reference)
    old_content: str   # full file content at old_hash via git show
    new_content: str   # full file content at new_hash via git show
    old_branch: str = ""   # reconstructed branch name for old version
    old_branch_index: int = -1  # 0-based position in branch (oldest=0)
    new_branch: str = ""   # reconstructed branch name for new version
    new_branch_index: int = -1  # 0-based position in branch (oldest=0)

class DiffService:
    def diff(self, old_hash: str, new_hash: str) -> DiffResult:
        # git show old_hash:rel_path  →  old_content
        # git show new_hash:rel_path  →  new_content
        # git diff old_hash:rel_path new_hash:rel_path  →  text
```

`old_content` and `new_content` provide the full file text that the `DiffPanel` uses for side-by-side alignment. The `text` (unified diff) is retained as a fallback and for logging.

The caller is responsible for ordering `old_hash` / `new_hash` by `topo_rank` (lower = older) before calling `diff()`. `MainWindow.run_diff()` performs this sort automatically.

`old_branch` / `new_branch` and their corresponding `*_branch_index` are populated by `MainWindow.run_diff()` from the loaded graph model (`VersionNode.reconstructed_branch` and `VersionNode.per_branch_index`). `per_branch_index` is 0-based (0 = oldest commit on that branch); the UI displays it as 1-based (`per_branch_index + 1`) to match ClearCase convention.

---

## 4. Display Graph

The UI never renders the raw `GraphModel` directly. It always renders a `DisplayGraph` produced by `CollapseModel.build()`.

```python
@dataclass(frozen=True)
class DisplayNode:
    id: str
    kind: Literal["version", "run"]
    branch: str
    per_branch_index: int
    topo_rank: int          # used for stable Y-axis ordering
    label: str
    source_hashes: tuple[str, ...]

@dataclass(frozen=True)
class DisplayEdge:
    src: str
    dst: str
    kind: Literal["main", "branch", "merge"]
    label: str
```

The `DetailPanel` traces back to the raw `VersionNode` via `source_hashes[0]` when the user clicks a version node.

---

## 5. Layout Layer

`TreeLayout` maps `DisplayGraph` → `LayoutGraph` (pixel coordinates) without any Qt dependency.

### 5.1 Row assignment

`_row_by_node()` sorts nodes by `(topo_rank, branch, id)`. Using `topo_rank` (a global topological counter) instead of the per-branch `per_branch_index` ensures cross-branch Y positions are consistent with commit history order.

### 5.2 Column assignment — current (static, v1)

`_branch_order()` starts from a hint derived from `GraphModel.branches` insertion order, then appends unseen branches. Each branch occupies one fixed column for the entire height of the canvas. This produces wide layouts when many branches exist, because:

- Every branch occupies its full-height column regardless of how many rows it actually has nodes in.
- A branch that only exists at rows 50–60 still claims a full-height column, making fork edges span from row 50 all the way across to an empty column slot.
- Canvas width = `O(total branch count)`.

**Problem**: for a repository with 20 branches, even if each branch has only 5 commits, the canvas is 20 columns wide (3600 px at 180 px/col), with all fork lines spanning nearly the full width.

### 5.3 Column assignment — planned (dynamic, v2): Branch Interval Packing

**Core insight**: a column is a resource shared over time (rows). Two branches can share the same column if their row ranges do not overlap.

#### Definitions

- **Row range** of branch B: `[first_row(B), last_row(B)]` = min and max row indices of all nodes belonging to B in the current `DisplayGraph`.
- **Parent branch** of B: determined from "branch" edges in the `DisplayGraph`. If edge `(src, dst, "branch")` exists and `display_nodes[src].branch == B`, then `parent_branch(B) = display_nodes[dst].branch`.

#### Interval packing algorithm

```
Input:  branches with row ranges and parent relationships
Output: col[B] for every branch B

1. main branch → col 0

2. Build branch dependency order:
   Process branches in topological order of the branch tree
   (parent branch always before child branch).
   Within the same parent, sort by start_row ascending
   (earliest-forking branches get lower columns → stay closer to main).

3. For each branch B in dependency order:
   a. min_col = col[parent_branch(B)] + 1       # child must be right of parent
   b. For col = min_col, min_col+1, min_col+2, …:
      If col has no assigned branch whose row range overlaps
      [first_row(B) - GAP, last_row(B) + GAP]:
          col[B] = col; break
   (GAP = 1 row, to avoid headers of adjacent branches visually touching)

4. col_intervals[col].append((first_row(B), last_row(B), B))
```

#### Visual comparison

```
Scenario: main (rows 0–10), feat-A (rows 2–4, child of main),
          feat-B (rows 7–9, child of main), feat-C (rows 3–5, child of feat-A)

Static layout (4 columns, 720 px wide):
       col 0    col 1    col 2    col 3
row 0:  main
row 1:  main
row 2:  main   feat-A            
row 3:  main   feat-A   feat-C   
row 4:  main   feat-A   feat-C   
row 5:  main            feat-C   
row 6:  main                     
row 7:  main            feat-B   
row 8:  main            feat-B   
row 9:  main            feat-B   
fork edge (main→feat-B): 2 columns wide

Dynamic layout (3 columns, 540 px wide):
       col 0    col 1    col 2
row 0:  main
row 1:  main
row 2:  main   feat-A            
row 3:  main   feat-A   feat-C   
row 4:  main   feat-A   feat-C   
row 5:  main            feat-C   
row 6:  main                     
row 7:  main   feat-B            ← reuses col 1 (no overlap with feat-A rows 2–4)
row 8:  main   feat-B            
row 9:  main   feat-B            
fork edge (main→feat-B): 1 column wide
```

feat-C must be in col ≥ 2 (child of feat-A which is in col 1). feat-B and feat-A are siblings (both children of main) with non-overlapping row ranges, so they share col 1. The result: 3 columns instead of 4 for this example, and fork edges are always exactly 1 column wide.

For a repository with 20 branches that all fork from main at different times with non-overlapping ranges: static layout → 20 columns; dynamic layout → 1 column (all branches share col 1, multiplexed over time). Canvas width = `O(max branching depth)`.

#### Branch header positioning

With dynamic layout, branch headers are **no longer pinned to the top of the canvas**. Instead, each branch header is placed just above the branch's first (topologically earliest) node:

```
header.rect.y = top_margin + first_row(B) * row_height - header_height - 4
header.rect.x = left_margin + col[B] * col_width - header_width / 2
```

This mirrors ClearCase lsvtree behavior: the branch label appears at the point where the branch forks, not floating at the top of an empty column.

#### Edge routing implications

- **Fork (branch) edges**: with dynamic columns, the fork edge from the parent commit to the first commit of the child branch is always exactly 1 column wide (horizontal or 1-step diagonal). This eliminates the "stretched fork" problem.
- **Merge edges**: interval packing shortens merge edges on average, but the column ORDER within each packing still affects how many merge edges cross each other. Column ordering optimization is addressed in §5.4.
- **Cross-branch interference**: a straight line between two nodes may still cross intermediate branch columns if column order is not optimized. Curve routing (Bézier waypoints) is deferred.

#### Implementation plan

Changes confined to `layout/tree_layout.py`:

| Step | Change |
|------|--------|
| New method `_row_ranges(display_graph, row_by_node)` | Returns `dict[branch, (first_row, last_row)]` |
| New method `_parent_branch_map(display_graph)` | Returns `dict[branch, parent_branch]` from "branch" edges |
| New method `_pack_columns(branches, row_ranges, parent_map, main_branch)` | Interval packing → `dict[branch, int]` |
| Update `layout()` | Replace `_branch_order()` call with `_pack_columns()` call |
| Update `headers` block | Position headers at `first_row` instead of `top_margin` |

`LayoutGraph`, `LayoutNode`, `LayoutEdge`, `BranchHeader`, and all UI layers are **unchanged** — column numbers flow through the same pixel formula `x = left_margin + col * col_width`.

### 5.4 Column ordering — merge-aware crossing minimization (v3)

Interval packing (§5.3) determines the **number** of columns and which branches may share a column, but does not constrain the **relative order** of branches within those columns. Two branches assigned to non-shared columns can still be placed in either relative position. The wrong ordering causes merge lines to cross.

#### 5.4.1 Crossing definition

Two merge edges M1 = (A → B) and M2 = (C → D) cross if and only if both conditions hold:

```
Row ranges overlap:
    max(row_A, row_B) > min(row_C, row_D)
    AND min(row_A, row_B) < max(row_C, row_D)

Column ranges interleave (edges go in opposite horizontal directions):
    min(col_A, col_B) < min(col_C, col_D) < max(col_A, col_B) < max(col_C, col_D)
    OR the symmetric case
```

In a version tree where merge edges always run from a feature branch (higher column) toward main or another target (lower column), crossings occur when two merge edges "swap" their relative column order between source and target rows.

#### 5.4.2 Algorithm

Three phases, applied after interval packing produces the initial column assignment:

---

**Phase A — Merge topology analysis**

Extract branch-level merge relationships from `DisplayGraph.edges`:

```python
merge_pairs: list[tuple[str, str]]   # (src_branch, dst_branch) for each merge edge
merge_partners: dict[str, set[str]]  # branch → set of branches it merges with
```

Also compute for each merge edge its row range — the span from source node's row to target node's row.

---

**Phase B — Merge-cost column selection**

Modify `_pack_columns` so that when multiple candidate columns satisfy the packing constraints, the one with the lowest **merge cost** is chosen rather than simply the lowest column index.

For branch B being assigned to column `c`, with all previously placed merge partners P already at column `col(P)`:

```
merge_cost(B, c) = Σ  |c - col(P)| × overlap_weight(B, P)
                  P ∈ merge_partners[B] ∩ placed

overlap_weight(B, P) = length of row-range intersection of B and P
                       (longer shared row range → more visual prominence)
```

**Selection rule**: among all candidate columns `c ≥ parent_col + 1` that satisfy the packing constraint, choose the `c` minimising `merge_cost(B, c)`.

**Intuition**: branches that merge into each other are pulled toward adjacent columns, shortening merge lines and reducing the chance of crossing intermediate branches.

---

**Phase C — Local swap refinement**

Phase B is greedy (placement order affects result). A post-hoc swap pass improves the global assignment:

```
repeat:
    improved = False
    for each pair of branches (A, B) where neither is an ancestor of the other:
        if swap(col[A], col[B]) satisfies all constraints:
            Δ = crossing_count_after - crossing_count_before
            if Δ < 0:
                apply swap
                improved = True
until not improved
```

**Constraint check for swap(A, B)**:

1. Parent constraint: `col[parent(A)] < col[B]` and `col[parent(B)] < col[A]` (swapped positions must still be right of each branch's parent).
2. Child constraint: all children of A must have columns > `col[B]`, and vice versa.
3. Packing constraint: in column `col[B]`, no existing occupant has a row range overlapping A (with GAP=1), and symmetrically for column `col[A]` and B.

**Crossing count** (used to evaluate Δ):

Iterate all pairs of merge edges `(M1, M2)` and apply the crossing condition from §5.4.1. O(M²) per evaluation, where M = number of merge edges. For typical repos (M < 100) this is < 0.1 ms.

---

#### 5.4.3 Complexity

| Phase | Cost | Typical runtime |
|-------|------|-----------------|
| A — topology | O(E) | negligible |
| B — cost selection | O(B × M) per branch, O(B² × M) total | < 1 ms |
| C — swap refinement | O(B² × M²) per pass, 2–3 passes typical | < 5 ms |

B = branch count, M = merge edge count, E = total edge count. All within the layout thread; no UI impact.

#### 5.4.4 Visual impact

```
Before (greedy column, 3 crossings):      After (merge-aware, 0 crossings):

col:  0      1      2      3             col:  0      1      2      3
      main   A      B      C                   main   C      B      A

merge C→main ──────────────╮            merge C→main ──╮
merge B→main ─────────╮   │            merge B→main ──────╮
merge A→main ─────╮   │   │            merge A→main ──────────╮
                  ↓   ↓   ↓                              ↓   ↓   ↓
         3 crossings (lines tangle)          0 crossings (lines fan cleanly)
```

The algorithm re-orders A, B, C so that branches merging into main are sorted by merge row, ensuring merge lines fan out without crossing.

#### 5.4.5 Implementation plan

Changes confined to `layout/tree_layout.py` and its tests:

| Step | Change |
|------|--------|
| New method `_merge_branch_pairs(display_graph)` | Returns `list[(src_branch, dst_branch)]` and `dict[branch, set[branch]]` |
| Modify `_pack_columns` signature | Add `merge_partners` parameter |
| Modify `_pack_columns` column selection | Replace "lowest available" with `argmin merge_cost` over candidates |
| New method `_swap_optimize_columns(col, row_ranges, parent_map, merge_partners, merge_edges)` | Phase C local swap, returns updated `col` dict |
| Update `layout()` | Call `_merge_branch_pairs()`, pass result into `_pack_columns()`, then call `_swap_optimize_columns()` |
| New tests in `test_tree_layout.py` | `test_no_crossing_simple_fan`, `test_swap_reduces_crossings`, `test_crossing_count_formula` |

`LayoutGraph`, `LayoutNode`, `LayoutEdge`, and all UI layers are **unchanged**. The algorithm outputs the same `dict[branch, int]` column map; only the values differ.

### 5.5 Layout constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `branch_col_width` | 180 px | Horizontal distance between branch columns |
| `row_height` | 54 px | Vertical distance between version rows |
| `header_height` | 32 px | Height reserved for branch header rectangles |
| `top_margin` | 48 px | Space above the first node row |
| `left_margin` | 40 px | Space left of the first column |
| `node_radius` | 10 px | Version node circle radius |
| `branch_header_width` | 90 px | Branch header rectangle width |
| `branch_header_height` | 18 px | Branch header rectangle height |

### 5.6 Edge routing refinement (v1.5)

The Phase 7 layout optimizes branch columns, merge crossing count, merge span, and width. It does **not** yet solve the final rendering problem where multiple edges may share the same visual path or pass through unrelated version-node circles.

Phase 9 adds a routing layer after node coordinates are known and before `EdgeItem` renders the path.

#### 5.6.1 Problem

Current `LayoutEdge` has only:

```python
src: str
dst: str
kind: str
label: str
start: Point
end: Point
```

This means every edge is rendered as a single direct path from `start` to `end`. In dense merge histories:

- multiple merge edges can overlap exactly or nearly exactly;
- click hit-testing on overlapped edges is ambiguous;
- a merge edge can visually pass through intermediate version-node circles;
- the selected edge endpoint overlay is correct, but the user may not be able to visually identify which overlapped edge was selected.

#### 5.6.2 Design goal

Route edges with minimal visual disruption:

1. Preserve the existing Sugiyama-style branch column layout.
2. Do not widen the branch layout to solve rendering-only overlap.
3. Separate visually overlapped merge edges using stable Bezier curve offsets.
4. Avoid unrelated node circles where practical.
5. Preserve edge hit-testing and edge selection behavior.
6. Keep main/branch edges simple unless they demonstrably overlap or pass through nodes.

#### 5.6.3 Data model extension

Extend `LayoutEdge` with optional route data:

```python
route_kind: Literal["line", "quadratic", "cubic"] = "line"
control_points: tuple[Point, ...] = ()
route_index: int = 0
route_group_size: int = 1
```

Rules:

- `route_kind == "line"` uses the current direct line path.
- `route_kind == "quadratic"` uses one control point.
- `route_kind == "cubic"` is reserved for future routing and uses two control points.
- `route_index` and `route_group_size` are diagnostic fields that explain bundled/separated edge routing.

#### 5.6.4 Route grouping

Build route groups after all node centers are known:

```python
route_key = (
    min(src_col, dst_col),
    max(src_col, dst_col),
    min(src_row, dst_row),
    max(src_row, dst_row),
    edge.kind,
)
```

Edges in the same or near-identical route group are candidates for separation.

For Phase 9, only exact route groups are mandatory. Near-overlap grouping is optional and can be added later using geometric similarity.

#### 5.6.5 Curve offset

For each route group with `k > 1`, assign deterministic offsets. Same-path merge groups must not leave any edge at zero offset, because avoiding overlap is more important than preserving the shortest straight path.

```python
offset_slot = index - (k - 1) / 2
if offset_slot == 0:
    offset_slot = 0.5

spacing = min(
    EDGE_MAX_PARALLEL_SPACING,
    EDGE_BASE_PARALLEL_SPACING + k * EDGE_GROUP_SPACING_STEP,
)
offset_px = offset_slot * spacing
```

Implemented constants:

```python
EDGE_BASE_PARALLEL_SPACING = 12.0
EDGE_GROUP_SPACING_STEP = 3.0
EDGE_MAX_PARALLEL_SPACING = 30.0
MIN_ROUTE_CONTROL_SEPARATION = 12.0
EDGE_OBSTACLE_PADDING = 8.0
MAX_ROUTE_OFFSET = 96.0
MIN_EDGE_STROKE_WIDTH = 1.0
```

For a line from `start` to `end`, compute the unit perpendicular vector `(px, py)`. The quadratic control point is:

```python
mid = (start + end) / 2
control = mid + perpendicular * offset_px
```

Visual stroke width is adaptive:

```python
base = 2.0 if kind == "merge" else 1.8
stroke_width = base if k <= 2 else max(MIN_EDGE_STROKE_WIDTH, base - 0.18 * (k - 2))
```

The selection/highlight stroke can still be wider than the normal stroke. The hit-test shape remains wider than the visual stroke so thin routed edges remain clickable.

If the direct line intersects an unrelated node circle, choose a deterministic side and apply at least `EDGE_BASE_PARALLEL_SPACING`.

#### 5.6.6 Mirror-side selection

After the initial offset magnitude is known, the router must evaluate the preferred side and its symmetric mirror side:

```python
preferred_offset = offset_px
mirrored_offset = -offset_px
```

Each candidate is approximated as a sampled quadratic polyline and scored against already routed edges:

```python
score =
    route_intersection_count * ROUTE_INTERSECTION_WEIGHT
    + node_obstacle_hit_count * ROUTE_OBSTACLE_WEIGHT
    + polyline_length * ROUTE_LENGTH_WEIGHT
```

Implemented constants:

```python
ROUTE_INTERSECTION_WEIGHT = 1000.0
ROUTE_OBSTACLE_WEIGHT = 10000.0
ROUTE_LENGTH_WEIGHT = 0.001
ROUTE_SAMPLE_STEPS = 10
```

If the mirror side has a strictly lower score, use the mirror offset. This rule lets an edge draw from the opposite side when doing so reduces visible crossings. Node obstacle hits are weighted higher than edge crossings, so the router should not avoid one line crossing by routing through a version-node circle.

This remains a bounded local heuristic. It does not solve global spline routing, but it improves the common case where the visually cleaner side is the exact mirror of the current curve.

#### 5.6.7 Node obstacle avoidance

For each edge, check every non-endpoint version node:

1. Compute distance from node center to the direct segment `start → end`.
2. If `distance < node_radius + EDGE_OBSTACLE_PADDING`, the edge is considered to pass through or too close to that node.
3. Increase the curve offset away from the obstacle side.
4. Clamp absolute offset to `MAX_ROUTE_OFFSET`.

This is a local obstacle-avoidance heuristic, not a full global router. It is acceptable because the primary layout already keeps nodes in stable branch columns.

#### 5.6.8 EdgeItem rendering

`EdgeItem` should render based on `LayoutEdge.route_kind`:

- `line`: current direct path and arrowhead.
- `quadratic`: `QPainterPath.quadTo(control, end_without_arrow)` plus arrowhead at the tangent direction near destination.
- `cubic`: future extension.

The path item itself must use `NoBrush`; the arrowhead is a separate polygon child item. This prevents Qt from filling the area enclosed by a curved path and the arrowhead polygon.

`EdgeItem.shape()` must continue to return a widened stroked path so separated curves remain easy to click.

#### 5.6.9 Edge selection interaction

Edge selection behavior remains:

- click one edge → highlight that exact edge;
- click another edge → previous highlight and endpoint overlay disappear;
- overlay shows source/destination version label, short hash, and branch name using ` ｜ ` separators and monospace field alignment.
- the scene owns a single cached edge endpoint overlay item; selecting another edge updates this cached overlay in place, invalidates the old/new overlay regions, and repaints the attached views so stale endpoint information cannot remain visible.

Phase 9 must ensure that separated curves have separate geometry so the clicked/highlighted curve is visually identifiable.

#### 5.6.10 Non-goals

- No Graphviz/dot dependency.
- No full spline router.
- No orthogonal global edge router.
- No branch column changes solely for edge rendering.
- No guarantee that every possible edge avoids every node in pathological graphs.

---

## 6. UI Layer

### 6.0 Main Window Layout

MainWindow uses a horizontal QSplitter as the central widget, with the project navigator on the left and the version-tree stack on the right:

```
QMainWindow
  ├── toolbar
  ├── central widget: QSplitter (horizontal)
  │     ├── left: CollapsibleNavigator
  │     │          ├── ProjectNavigator (QTreeWidget)
  │     │          └── toggle button strip (18 px, right edge)
  │     └── right: QStackedWidget
  │                 ├── empty state label
  │                 └── GraphView
  ├── right dock: Details
  └── bottom dock: DiffPanel
```

The central area is a three-panel `QSplitter(Horizontal)`:

```
┌──────────────┬──────────────────────────┬──────────────┐
│ CollapsibleNav│  QStackedWidget          │CollapsibleDetail│
│  (left panel) │  (version tree / empty) │ (right panel) │
└──────────────┴──────────────────────────┴──────────────┘
│                    Diff (bottom dock)                   │
└─────────────────────────────────────────────────────────┘
```

**Default state** (no project open):

```
┌──┬──────────────────────────────────┬──────────────────┬──┐
│▶ │  version tree / empty state      │  Detail Panel    │▶ │
└──┴──────────────────────────────────┴──────────────────┴──┘
 nav                                   detail expanded   detail btn
 (18px)                                (≈200px)          (18px)
```

**Project open + nav expanded**:

```
┌───────────┬──┬──────────────────────┬──────────────────┬──┐
│ ProjectNav│◀ │  version tree canvas │  Detail Panel    │▶ │
│  (≈200px) │  │                      │  (≈200px)        │  │
└───────────┴──┴──────────────────────┴──────────────────┴──┘
```

**Both panels collapsed**:

```
┌──┬────────────────────────────────────────────────────┬──┐
│▶ │  version tree canvas (maximum width)               │◀ │
└──┴────────────────────────────────────────────────────┴──┘
```

All panels use `CollapsiblePanel` with an 18 px toggle strip. Neither panel is ever fully removed from the layout — they always hold at least 18 px so the toggle affordance is always reachable. `QDockWidget` is no longer used for navigator or detail; only the Diff panel remains as a bottom dock.

The project navigator is opened only in project mode. In single-file mode it remains collapsed unless a project has already been opened in the session.

### 6.1 GraphScene

`GraphScene` (subclass of `QGraphicsScene`) owns the item dictionary `item_by_id: dict[str, VersionNodeItem | CollapsedRunItem]` and provides:

- **Hit-testing**: `mousePressEvent` calls `itemAt()` and walks up to the parent item if a child (e.g. label text) was hit. Emits `nodeClickedWithModifiers(node_id, modifiers)`.
- **Edge hit-testing**: if a rendered `EdgeItem` is clicked, emits `edgeClicked(src_id, dst_id)` and updates scene-local edge selection state.
- **Double-click**: `mouseDoubleClickEvent` emits `runDoubleClicked(run_id)` for collapsed run items.
- **Selection**: `set_selection(node_ids)` applies yellow highlight (thick amber border) to selected version nodes.
- **Edge selection**: `set_edge_selection(src_id, dst_id)` highlights exactly one edge and displays a small overlay in the version tree area with both endpoint labels, short hashes, and branch names. Selecting another edge removes the previous overlay and highlight. The endpoint rows must use a fixed-width visual format:

  ```text
  from: <version> ｜ <short-hash> ｜ <branch>
  to:   <version> ｜ <short-hash> ｜ <branch>
  ```

  The overlay text must use a monospace font and padded fields so the `from` and `to` rows align vertically. The separator is ` ｜ ` to make field boundaries visually clear.
- **Edge overlay refresh**: `GraphScene` must cache one endpoint overlay panel and update it in place when edge selection changes. `set_edge_selection()` must hide or replace the previous content before showing the new endpoint data, invalidate both the old and new overlay bounding regions, call scene update, and request viewport repaint on attached views. This keeps edge click feedback fast and prevents stale overlay pixels from staying on screen.
- **Search highlight**: `highlight_node(node_id)` applies an amber fill and scrolls the view to the node.
- **Level-of-detail**: `update_lod(zoom)` hides all node labels when `zoom < 0.35`, reducing visual clutter at low magnification.

### 6.2 GraphView

`GraphView` (subclass of `QGraphicsView`) uses `NoDrag` mode so that left-click events reach the scene for node selection. Panning is implemented with the **middle mouse button**: press to start, drag to pan, release to stop. This avoids the conflict between `ScrollHandDrag` mode and scene click events.

Zoom is anchored under the mouse cursor (`AnchorUnderMouse`). After `fitInView()`, `zoom_factor` is updated from `self.transform().m11()` rather than hardcoded to `1.0`.

### 6.3 Items

| Item | Qt base | Visual |
|------|---------|--------|
| `VersionNodeItem` | `QGraphicsEllipseItem` | Blue circle; yellow thick border when selected |
| `CollapsedRunItem` | `QGraphicsRectItem` | Light grey rectangle, dashed border |
| `BranchHeaderItem` | `QGraphicsRectItem` | Blue rectangle at column top |
| `EdgeItem` | `QGraphicsPathItem` | Dark grey (main), blue (branch), red dashed (merge); line or routed Bezier curve; bright selected pen when edge-selected |

All items store a `label_item: QGraphicsSimpleTextItem` child for LOD visibility toggling.

For routed edges, `EdgeItem` consumes `LayoutEdge.route_kind` and `LayoutEdge.control_points`. Edge hit-testing is based on the rendered `QPainterPath.shape()`, not a separate straight-line proxy, so visual selection and click selection remain consistent.

### 6.4 MainWindow state

| Field | Type | Purpose |
|-------|------|---------|
| `current_project_root` | `Path \| None` | Currently opened project repository root |
| `current_file` | `Path \| None` | Currently opened file |
| `current_project_tree` | `ProjectTree \| None` | Cached tracked-file directory tree for the navigator |
| `project_navigator_visible` | `bool` | Whether the project navigator dock is visible |
| `current_mode` | `str` | `"key"` or `"full"` |
| `collapse_enabled` | `bool` | Whether runs are collapsed |
| `expanded_runs` | `frozenset[str]` | Run IDs that have been individually expanded |
| `selected_versions` | `list[str]` | Up to 2 selected version node IDs (click order) |
| `current_run` | `str \| None` | Currently focused collapsed run |
| `_pending_run` | `str \| None` | Run to restore as `current_run` after async reload |
| `current_layout` | `LayoutGraph \| None` | Last rendered layout |
| `current_graph` | `GraphModel \| None` | Raw graph for detail lookups |

`_pending_run` solves the expand-then-collapse UX issue: `expand_run()` sets `_pending_run = run_id` before triggering async reload; `set_loaded_layout()` restores `current_run` from it, so "Collapse Run" remains enabled immediately after expansion completes.

### 6.5 CollapsiblePanel and CollapsibleNavigator

`CollapsiblePanel(QWidget)` is a generic collapsible sidebar base class. It wraps any `QWidget` with an 18 px toggle strip on one edge.

```python
class CollapsiblePanel(QWidget):
    collapseToggled = Signal(bool)  # True = collapsed, False = expanded

    def __init__(self, widget: QWidget, side: Literal["left", "right"] = "left"):
        ...
    def expand(self) -> None: ...
    def collapse(self) -> None: ...
    def toggle(self) -> None: ...
    @property
    def is_collapsed(self) -> bool: ...
```

**`side="left"`** (navigator): strip on right edge, ▶ = collapsed, ◀ = expanded.  
**`side="right"`** (detail): strip on left edge, ◀ = collapsed, ▶ = expanded.

`CollapsibleNavigator(CollapsiblePanel)` extends the base and adds:
- `navigator: ProjectNavigator` attribute
- `fileSelected: Signal(Path)` forwarded from `ProjectNavigator`
- `set_project_tree(tree)` helper

The central `QSplitter` holds three widgets in order:
```
index 0: CollapsibleNavigator  (side="left",  default collapsed)
index 1: QStackedWidget        (stretch=1, takes all remaining space)
index 2: CollapsiblePanel      (side="right", wraps DetailPanel, default expanded)
```

**Width management (MainWindow):**

`_nav_expanded_width` and `_detail_expanded_width` (both default 200 px) store the last-used expanded widths. `_on_nav_collapse_toggled` and `_on_detail_collapse_toggled` call `QSplitter.setSizes([n, center, d])` keeping the opposite panel's width unchanged. `_on_splitter_moved` updates the stored widths when the user drags a handle while a panel is expanded.

**View menu toggles:**
- `View → Project Navigator` (checkable) — synced to `CollapsibleNavigator.collapseToggled`
- `View → Detail Panel` (checkable) — synced to `CollapsiblePanel.collapseToggled` for the detail panel

`CollapsibleNavigator(QWidget)` wraps `ProjectNavigator` inside a resizable left sidebar. It is the left child of the central `QSplitter`.

```
CollapsibleNavigator
  QHBoxLayout (no margins, no spacing)
    ├── ProjectNavigator   (hidden when collapsed, stretch=1)
    └── _toggle_btn        (QPushButton, fixed 18 px width, always visible)
```

**States:**

| State | navigator | button text | button tooltip |
|-------|-----------|-------------|----------------|
| Collapsed | hidden | ▶ | Expand project navigator |
| Expanded | visible | ◀ | Collapse project navigator |

**Signal:** `collapseToggled(bool)` — emitted on every toggle; `True` = just collapsed, `False` = just expanded.

**Public API:**

```python
expand()    # no-op if already expanded; shows navigator, updates button, emits signal
collapse()  # no-op if already collapsed; hides navigator, updates button, emits signal
toggle()    # calls expand() or collapse()
is_collapsed: bool  # property
set_project_tree(tree: ProjectTree)  # delegates to ProjectNavigator
fileSelected: Signal(Path)  # forwarded from ProjectNavigator
```

**Width management (MainWindow):**

`MainWindow` stores `_nav_expanded_width: int` (default 200 px).

```python
def _on_nav_collapse_toggled(self, collapsed: bool) -> None:
    total = self._nav_splitter.width()
    if collapsed:
        # save current expanded width before shrinking
        w = self._nav_splitter.sizes()[0]
        if w > _NAV_BTN_WIDTH:
            self._nav_expanded_width = w
        self._nav_splitter.setSizes([_NAV_BTN_WIDTH, total - _NAV_BTN_WIDTH])
    else:
        w = self._nav_expanded_width
        self._nav_splitter.setSizes([w, max(0, total - w)])
```

Dragging the splitter handle while expanded updates `_nav_expanded_width` via `splitterMoved`.

**Toolbar:** `Open Project…` action is added to the toolbar (next to `Open File…`) so users can open a project without navigating the menu.

**Visual behavior of ProjectNavigator (unchanged):**

- directory collapsed: `+ dirname`
- directory expanded: `- dirname`
- file: `  filename`
- current selected file: highlighted row

Collapsing the navigator must not clear `current_project_tree` or `current_file`; expanding it again restores the same directory expanded/collapsed state.

The version tree canvas remains single-file.

---

## 7. Background Workers

### ProjectTreeWorker

Runs project directory scanning in a `QRunnable`.

```python
@dataclass(frozen=True)
class ProjectLoadRequest:
    project_path: Path

@dataclass(frozen=True)
class ProjectLoadResult:
    repo_root: Path
    tree: ProjectTree
```

Worker pipeline:

```
ProjectLoadRequest(project_path)
  └─► GitRepo / project resolver
        └─► git rev-parse --show-toplevel
              └─► git ls-files -z
                    └─► ProjectTree
                          └─► ProjectNavigatorDock.set_project_tree()
```

Failure cases:

- selected directory is not inside a Git repository;
- `git ls-files` fails;
- repository has no tracked files.

Failures emit `signals.failed(str)` and are displayed in the empty-state label/status bar without modifying the currently loaded file graph.

### GraphLoaderWorker

Runs the full pipeline (HistoryLoader → BranchRebuilder → KeySelector → CollapseModel → TreeLayout) in a `QRunnable`. On completion emits `GraphLoaderSignals.loaded(GraphLoadResult)`. On failure emits `GraphLoaderSignals.failed(str)`.

`GraphLoadResult` carries both `layout: LayoutGraph` and `graph: GraphModel` so the main thread can look up raw commit metadata without re-running git.

### DiffLoaderWorker

Runs `DiffService.diff()` in a `QRunnable`. Emits `DiffLoaderSignals.loaded(DiffResult)` or `.failed(str)`. `MainWindow.run_diff()` sorts the two selected hashes by `topo_rank` before dispatching the worker, ensuring `old_hash` is always the topologically earlier commit.

---

## 7a. DiffPanel Design

### Layout

```
DiffPanel (QWidget)
  QVBoxLayout
  ├── header_row (QWidget, QHBoxLayout)          ← outside splitter
  │     ├── old_label  "Old  aabb1234  —  foo.py  @ main/3"  (stretch=1)
  │     └── new_label  "New  ccdd5678  —  foo.py  @ feature-x/1"  (stretch=1)
  └── content_row (QWidget, QHBoxLayout)
        ├── splitter (QSplitter, Horizontal)
        │     ├── left_pane  (QPlainTextEdit, old version)
        │     └── right_pane (QPlainTextEdit, new version)
        └── ruler (DiffOverviewRuler, 12 px fixed width)
```

Visual layout:

```
┌─────────────────────────────────────────────────────────┐
│ Old  aabbccdd1234  —  src/foo.py  │ New  eeff5678  …   │ ← header_row
├──────────────────────────┬────────┴─────────────────────┼──┐
│ Left pane (old version)  │ Right pane (new version)      │  │
│                          │                               │  │
│  line 1  (white)         │  line 1  (white)              │  │ ← ruler
│  line 2  [red bg]        │  line 2  [blue bg]            │█ │   height =
│  line 3  (white)         │  line 3  (white)              │  │   splitter
│  (empty)                 │  line 4  [blue bg]            │  │   height
│  …                       │  …                            │  │
│                          │                               │  │
├──────────────────────────┴───────────────────────────────┘  │
│ [h-scrollbar]                                    [v-scroll]  │
└──────────────────────────────────────────────────────────────┘
```

**Why headers are outside the splitter**: placing labels inside each pane's container (as in v1) causes the ruler height to include the label height, so the ruler's proportional coordinate mapping is offset upward by the label height. Moving headers into a separate `header_row` above the splitter ensures `ruler.height() == splitter.height() == pane.height()`, so the coordinate mapping is exact.

### Components

| Widget | Class | Role |
|--------|-------|------|
| Root | `DiffPanel(QWidget)` | Top-level container |
| Header row | `QWidget` + `QHBoxLayout` | Separate row above splitter |
| Old label | `QLabel` | Hash + path for old version |
| New label | `QLabel` | Hash + path for new version |
| Content row | `QWidget` + `QHBoxLayout` | Splitter + ruler side-by-side |
| Splitter | `QSplitter(Horizontal)` | Resize left/right panes |
| Left pane | `QPlainTextEdit` | Old file content, read-only, no-wrap |
| Right pane | `QPlainTextEdit` | New file content, read-only, no-wrap |
| Overview ruler | `DiffOverviewRuler(QWidget)` | 12 px strip; red marks + double-click nav |

### Color scheme

| Content | Left pane | Right pane |
|---------|-----------|------------|
| Changed line | `#fee2e2` (red) | `#dbeafe` (blue) |
| Unchanged line | `#ffffff` (white) | `#ffffff` (white) |
| Empty padding line | system default | system default |

### Line alignment algorithm

Uses `difflib.SequenceMatcher(autojunk=False)` on `old_content.splitlines()` vs `new_content.splitlines()`.

`_align_sides(old_lines, new_lines) → (left, right, diff_ranges)`:

| Opcode | Left side | Right side |
|--------|-----------|------------|
| `equal` | line, white | line, white |
| `replace` | old lines red; pad with empty if shorter | new lines blue; pad with empty if shorter |
| `delete` | old lines red | empty lines, default bg |
| `insert` | empty lines, default bg | new lines blue |

Padding ensures left and right always have the same total line count (required for synchronized scrolling). `diff_ranges` lists `(start_line, end_line)` for every non-equal block, passed to `DiffOverviewRuler.set_ranges()`.

### Synchronized scrolling

Both panes connect their `verticalScrollBar().valueChanged` and `horizontalScrollBar().valueChanged` to shared handlers guarded by `_syncing: bool` to prevent feedback loops. Mouse-wheel events drive the scroll bar value, which triggers the handler automatically.

### Overview ruler (`DiffOverviewRuler`)

A narrow `QWidget` (12 px fixed width) placed in `content_row` alongside the splitter. Its height therefore exactly equals the pane height, with no offset from headers.

**Rendering** (`paintEvent`):
1. Fill background `#f8fafc`.
2. For each `(start, end)` in `_ranges`, compute pixel range:
   - `y1 = int(start × h / total_lines)`
   - `y2 = max(y1 + 2, int(end × h / total_lines))` (minimum 2 px height)
3. Draw filled `#ef4444` rectangle `(1, y1, width-2, y2-y1)`.
4. The ruler never scrolls — it always represents the full document.

**Data API**: `set_ranges(total_lines: int, ranges: list[tuple[int, int]])` — stores data and calls `update()`.

**Double-click navigation** (`mouseDoubleClickEvent`):
1. Compute `target_line = int(event.pos().y() / height() × total_lines)`.
2. Find the nearest diff block: scan `_ranges` for a block containing `target_line`; if none, pick the block with the smallest distance to `target_line`.
3. Emit `Signal jumpRequested(int)` with the block's `start_line`.
4. `DiffPanel._jump_to_line(line)` slot: for each pane, create a `QTextCursor` on `document().findBlockByLineNumber(line)`, call `setTextCursor()` then `centerCursor()`, guarded by `_syncing` to avoid double-scroll.

---

## 8. Interaction State Machines

### 8.1 Version selection

```
NoSelection
  left-click version node  →  OneSelected(v1)
  left-click run node      →  RunFocused(run)

OneSelected(v1)
  left-click version node  →  OneSelected(v2)       # replaces selection
  Ctrl/Shift+click version →  TwoSelected(v1, v2)   # appends, keeps last 2
  left-click blank         →  NoSelection

TwoSelected(v1, v2)
  left-click version node  →  OneSelected(v3)
  Ctrl/Shift+click version →  TwoSelected(v2, v3)
  Diff action              →  run DiffLoaderWorker(v_older, v_newer)
```

Diff action is only enabled when exactly 2 concrete version nodes are selected. Collapsed run nodes do not participate in diff selection.

### 8.1b Edge selection

```
NoEdgeSelected
  left-click edge e1      →  EdgeSelected(e1)

EdgeSelected(e1)
  left-click edge e2      →  EdgeSelected(e2)       # replaces highlight and endpoint info
  left-click version node →  NoEdgeSelected         # node selection owns the visible focus
  left-click blank        →  NoEdgeSelected
```

Edge selection clears version-node diff selection so the canvas has one visible focus mode at a time. Edge endpoint information is displayed in the version tree area rather than the right-side detail dock, because it explains the clicked line directly in the graph context.

### 8.1c Project navigation

```
NoProject
  Open Project directory    →  LoadingProject

LoadingProject
  ProjectTree loaded        →  ProjectLoaded(root)
  ProjectTree failed        →  NoProject + error message

ProjectLoaded(root)
  click + directory         →  DirectoryExpanded(dir)
  click - directory         →  DirectoryCollapsed(dir)
  click file                →  LoadingFile(file)
  hide navigator dock       →  ProjectLoaded(root), navigator hidden
  show navigator dock       →  ProjectLoaded(root), navigator restored

LoadingFile(file)
  GraphLoadResult loaded    →  FileGraphVisible(file)
  GraphLoadResult failed    →  ProjectLoaded(root) + error message
```

Project state and file graph state are deliberately separate. A failed file graph load must not clear the project navigator, and hiding the navigator must not unload the current file graph.

### 8.2 Collapse / expand

```
run node visible (collapsed)
  double-click / "Expand Run" action  →  reload with run_id added to expanded_runs
  "Collapse Run" action               →  (disabled — run is not yet expanded)

run expanded (individual nodes visible)
  "Collapse Run" action               →  reload with run_id removed from expanded_runs
  "Expand Run" action                 →  (disabled — already expanded)
```

`expanded_runs` is a `frozenset` in `MainWindow` and is passed immutably to `CollapseModel.build()`. Mode switches (Key ↔ Full) and reloads preserve `expanded_runs`.

### 8.3 View mode

```
Key mode  ←──────────── toggle ────────────→  Full mode
    │                                              │
    ▼                                              ▼
CollapseModel (collapse enabled or disabled) ←── toggle Collapse
    │
    ▼
Individual run expand/collapse (preserved across mode switches)
```

Switching Key ↔ Full or toggling Collapse does **not** re-run `git log`; it only rebuilds the display graph and layout from the cached `GraphModel`.

---

## 9. Phase Implementation Plan

### Phase 1 — Core layer
Git history loading, GraphModel, BranchRebuilder, KeySelector, CollapseModel, DiffService. No Qt dependency.

### Phase 2 — Minimal Qt shell
MainWindow, GraphView, GraphScene, background loading via QThreadPool, empty-window state, zoom/pan, branch/node/edge rendering.

### Phase 3 — Interactions
Two-version selection, DiffPanel, collapsed run display (`CollapsedRunItem`), single-run expand and re-collapse.

### Phase 4 — Polish
- **Search**: toolbar `QLineEdit`, hash-prefix / label matching, amber highlight + scroll-to.
- **Status bar warning**: partial key selection warning propagated from `KeySelector` through `GraphLoadResult.warning`.
- **Export PNG**: `QPixmap` + `QPainter` render of `QGraphicsScene`.
- **Level-of-detail**: labels hidden at zoom < 35% (`GraphScene.update_lod()`).

### Phase 6 — Dynamic Layout (Branch Interval Packing)

Replace static column assignment with dynamic interval packing (see §5.3):
- Implement `_row_ranges()`, `_parent_branch_map()`, `_pack_columns()` in `tree_layout.py`.
- Reposition branch headers to fork-point row instead of canvas top.
- Validate: canvas width for a 20-branch repo should be ≤ O(max nesting depth) × col_width.

### Phase 5 — Diff UX & Edge Arrows
- **Branch name resolution**: `GitRepo.current_branch()` via `git rev-parse --abbrev-ref HEAD`; passed to `BranchRebuilder` so `master`/`develop` repos are labeled correctly.
- **Edge arrowheads**: `EdgeItem` rewritten as `QGraphicsPathItem`; draws filled triangle arrowhead (9 × 5 px) at destination. Merge: red dashed 2 px; cross-branch: blue 1.8 px; same-branch: dark-gray 1.8 px.
- **Side-by-side diff**: `DiffPanel` rewritten as `QWidget`; left pane = old version (changed lines red `#fee2e2`), right pane = new version (changed lines blue `#dbeafe`), unchanged lines white; vertical + horizontal scroll sync.
- **Diff overview ruler**: `DiffOverviewRuler(QWidget)` — narrow strip (scrollbar-width) to the right of the splitter; red rectangles mark diff block positions proportional to total line count; bird's-eye view of the entire file.

### Phase 8 — Tag visibility and edge selection polish
- **Important tag visibility**: normal UI loads set `include_repo_tags=True`; core tests keep the default opt-in behavior.
- **Edge selection**: `GraphScene` tracks a single selected edge; `EdgeItem` supports selected styling; the scene displays endpoint version information as an overlay inside the version tree canvas.

### Phase 9 — Edge Routing Refinement

Goal: make overlapping merge lines distinguishable and reduce edge paths that pass through unrelated version-node circles, without changing branch column layout.

#### Phase 9.1 — Extend layout edge route model
- Add `route_kind`, `control_points`, `route_index`, and `route_group_size` to `LayoutEdge`.
- Default to current line behavior for backward compatibility.
- Add layout tests proving existing straight-line cases remain unchanged.

#### Phase 9.2 — Route grouping and parallel curve offsets
- Group same-path edges after node coordinates are known.
- Assign stable symmetric offsets for route groups with more than one edge.
- Convert grouped merge edges to quadratic Bezier routes.
- Add tests for two and three overlapping merge edges producing distinct control points.

#### Phase 9.3 — Node obstacle avoidance
- Implement segment-to-circle proximity detection for non-endpoint version nodes.
- If direct path intersects or nearly touches a node circle, apply deterministic curve offset.
- Clamp offset to `MAX_ROUTE_OFFSET`.
- Add tests proving a merge edge passing through an intermediate node receives a curve route.

#### Phase 9.4 — EdgeItem Bezier rendering and arrow tangent
- Render `quadratic` routes with `QPainterPath.quadTo()`.
- Compute arrowhead direction from the curve tangent near destination.
- Keep `shape()` widened around the actual rendered path.
- Add tests around path shape / route metadata where Qt graphics assertions are stable.

#### Phase 9.5 — Interaction validation
- Verify clicked edge and highlighted edge use the same routed path.
- Verify selecting a different routed edge clears the previous overlay.
- Verify endpoint overlay remains correct for routed merge edges.

#### Phase 9.6 — Mirror-side crossing reduction
- Score preferred and mirrored curve offsets before finalizing a routed edge.
- Choose the mirror side when it reduces route intersections without hitting unrelated version nodes.
- Keep the same offset magnitude so the branch layout width is unchanged.
- Add tests for mirror-side crossing reduction and obstacle-preserving side selection.

### Phase 10 — Project Directory Navigator

Goal: allow opening a whole Git project, browsing its tracked files through a dockable directory navigator, and loading a selected file into the existing version tree canvas.

#### Phase 10.1 — Project tree core model
- Add `ProjectTreeNode` and `ProjectTree` dataclasses in `core/project_tree.py`.
- Implement tracked-file tree construction from `git ls-files -z`.
- Unit tests:
  - flat files become first-level file nodes;
  - nested paths become directory nodes;
  - only tracked paths are present;
  - deterministic sorting: directories first, then files, case-insensitive by display name.

#### Phase 10.2 — Project loading worker
- Add `ProjectLoadRequest`, `ProjectLoadResult`, `ProjectLoaderWorker`.
- Resolve repository root using `git rev-parse --show-toplevel`.
- Load tree in a background worker.
- Worker failure must not clear the current graph.
- Tests with mocked Git repo / subprocess wrapper.

#### Phase 10.3 — ProjectNavigatorDock UI
- Add `ui/project_navigator.py`.
- Render first-level directories/files initially.
- Use explicit `+` / `-` indicators for directory expand/collapse.
- Emit `fileSelected(Path)` when a file node is clicked.
- Preserve `expanded_project_dirs` and selected file state when the dock is hidden and shown again.
- Tests for tree population, expand/collapse state, and file selection signal.

#### Phase 10.4 — MainWindow integration
- Add `Open Project...` action.
- Add View menu action to show/hide Project Navigator.
- On project load success, show navigator dock and keep graph canvas unchanged until a file is selected.
- On file selection, call existing `load_file()` path and reuse current graph pipeline.
- Status bar should show project root and selected file when project mode is active.
- Tests for project load success, file selection triggering `GraphLoaderWorker`, and navigator visibility toggling.

#### Phase 10.5 — UX validation
- Opening a project does not immediately consume the version tree canvas with a directory view.
- Hiding the navigator frees horizontal space for the version tree.
- Floating the navigator does not reload the current graph.
- Selecting another file clears version-node/edge selections from the old file graph.
- Large repositories remain responsive because project scanning runs in a worker and file histories load on demand.

---

## 10. Error Handling

All Git subprocess errors are raised as `GitCommandError` (a `RuntimeError` subclass carrying `command`, `cwd`, `returncode`, `stdout`, `stderr`). Workers catch all exceptions and emit `signals.failed(str(exc))`. `MainWindow._on_graph_failed()` displays the message in the empty-state label.

Non-fatal situations (partial key selection, very large graphs) produce a warning string in `GraphLoadResult.warning` displayed in the status bar.

---

## 11. Requirements Traceability

| Requirement | Implementation |
|-------------|---------------|
| GUI version tree browser | `MainWindow` + `GraphView` + `GraphScene` |
| Toolbar with actions | `MainWindow._create_toolbar()` — 13 actions |
| Click node → version details | `GraphScene` → `nodeClickedWithModifiers` → `DetailPanel.show_version()` |
| Select 2 versions → diff | `selected_versions` state + `DiffLoaderWorker` + `DiffPanel.show_diff()` |
| Side-by-side diff view | `DiffPanel` (`QSplitter` + 2× `QPlainTextEdit`); red/blue/white color scheme |
| Diff overview ruler | `DiffOverviewRuler.set_ranges()` → proportional red blocks in narrow right strip |
| Scroll sync in diff | `verticalScrollBar` + `horizontalScrollBar` cross-connected with `_syncing` guard |
| Collapse / expand runs | `CollapseModel` + `CollapsedRunItem` + `expand_run()` / `collapse_current_run()` |
| Zoom / pan | `GraphView` wheel zoom + middle-button pan + `fit_to_view()` |
| ClearCase visual style | Blue `BranchHeaderItem`, blue circle `VersionNodeItem`, red dashed merge `EdgeItem` |
| Edge arrowheads | `EdgeItem` (`QGraphicsPathItem`) — filled triangle at destination, color per edge kind |
| Branch name resolution | `GitRepo.current_branch()` → `BranchRebuilder(main_branch=...)` |
| Status bar | `GitLsvtreeStatusBar.set_loaded()` — file, mode, counts, zoom, warning |
| Search / locate | Toolbar search box → `GraphScene.highlight_node()` |
| Export | `MainWindow.export_png()` → `QPixmap` |
| Open project directory | `Open Project...` → `ProjectLoaderWorker` → `ProjectNavigatorDock.set_project_tree()` |
| Browse project first-level directory | `ProjectNavigatorDock` from `ProjectTree` |
| Expand/collapse directory with +/- | `ProjectNavigatorDock.expanded_project_dirs` |
| Select file from project navigator | `ProjectNavigatorDock.fileSelected(Path)` → existing `MainWindow.load_file()` |
| Hide / float navigator | `QDockWidget` features on `ProjectNavigatorDock` |
