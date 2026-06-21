# Edge Overlay Refresh Cache Plan

Timestamp: 2026-06-21 20:53:16 Asia/Shanghai

## Problem

[KNOWN] Clicking an edge currently creates a new endpoint overlay after removing the old overlay item.

[INFERRED] In Qt GraphicsView, removing and adding graphics items without explicitly invalidating the old and new repaint regions can leave stale pixels visible until a later repaint.

[KNOWN] The user-visible bug is that the old endpoint information can remain visible after selecting another edge.

## Scope

[KNOWN] This change affects only `GraphScene` edge endpoint overlay lifecycle and repaint behavior.

[KNOWN] It does not change edge routing, graph loading, detail panel, diff behavior, or layout.

## Design Requirement

[KNOWN] `GraphScene` should keep one cached endpoint overlay item for fast refresh.

[KNOWN] Selecting an edge must:

1. clear previous edge highlight;
2. update cached overlay text, size, and position for the new edge;
3. show the overlay;
4. invalidate old and new overlay regions;
5. request viewport repaint.

[KNOWN] Clearing edge selection must:

1. clear the selected edge highlight;
2. hide the cached overlay;
3. invalidate the previous overlay region;
4. request viewport repaint.

## Interface / Detailed Design

[KNOWN] Existing public scene methods remain unchanged:

```python
GraphScene.set_edge_selection(src_id: str, dst_id: str) -> None
GraphScene.clear_edge_selection() -> None
```

[KNOWN] Internal cached fields:

```python
GraphScene._edge_info_item: QGraphicsRectItem | None
GraphScene._edge_info_text_item: QGraphicsSimpleTextItem | None
```

[KNOWN] New or updated internal methods:

```python
GraphScene._ensure_edge_info_item() -> QGraphicsRectItem
GraphScene._update_edge_info_item(src_id: str, dst_id: str, edge_item: EdgeItem) -> None
GraphScene._refresh_region(*rects: QRectF) -> None
```

[INFERRED] `_refresh_region()` should call `invalidate(..., QGraphicsScene.SceneLayer.AllLayers)`, `update(...)`, and `view.viewport().update()` for attached views.

## TDD Plan

1. Update the existing edge-selection test to require overlay item reuse and changed text after selecting a second edge.
2. Add a test that monkeypatches `invalidate()` and `update()` to verify old/new overlay regions are refreshed on edge replacement.
3. Implement cached overlay lifecycle.
4. Run targeted app tests.
5. Run full regression tests and compile check.

## Acceptance Criteria

- [KNOWN] Selecting edge A then edge B leaves only one visible endpoint overlay.
- [KNOWN] The cached overlay item is reused instead of creating a second visible panel.
- [KNOWN] Overlay text changes from edge A endpoints to edge B endpoints.
- [KNOWN] Old and new overlay regions are invalidated/updated.
- [KNOWN] Clearing selection hides the cached overlay.
