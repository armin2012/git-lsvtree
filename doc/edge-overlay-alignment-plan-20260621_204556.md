# Edge Overlay Alignment Plan

Timestamp: 2026-06-21 20:45:56 Asia/Shanghai

## Scope

[KNOWN] This change only affects the edge endpoint overlay shown inside the version tree area after clicking an edge.

[KNOWN] It does not change graph loading, layout, diff selection, or edge routing.

## Design Requirement

[KNOWN] The overlay must display endpoint rows with clear field boundaries:

```text
from: <version> ｜ <short-hash> ｜ <branch>
to:   <version> ｜ <short-hash> ｜ <branch>
```

[KNOWN] Fields are:

- version label;
- short unique identifier, 12 characters;
- branch name.

[KNOWN] The separator is ` ｜ `.

[INFERRED] To make rows visually aligned, the overlay text should use a monospace font and fixed-width padded fields.

## Interface / Detailed Design

[KNOWN] Existing method:

```python
GraphScene._format_node_summary(node) -> str
```

[KNOWN] Updated contract:

```python
GraphScene._format_node_summary(node) -> str
```

[KNOWN] Returns a padded endpoint summary string:

```text
<label padded> ｜ <short-hash padded> ｜ <branch>
```

[KNOWN] `GraphScene._make_edge_info_item(...)` remains the overlay construction entry point.

[KNOWN] `_make_edge_info_item(...)` must set a monospace font on the `QGraphicsSimpleTextItem` used for the overlay text.

## TDD Plan

1. Add/update a unit test that checks `_format_node_summary()` contains ` ｜ ` separators and fixed-width padded fields.
2. Add/update a UI-scene test that checks the edge overlay contains aligned `from:` / `to:` rows using the separator.
3. Implement `_format_node_summary()` formatting.
4. Set a monospace font for the overlay text item.
5. Run targeted tests.
6. Run full regression tests.

## Acceptance Criteria

- [KNOWN] Edge overlay endpoint rows use ` ｜ ` separators.
- [KNOWN] Endpoint rows include version, short hash, and branch name.
- [KNOWN] Rows are generated with fixed-width field padding.
- [KNOWN] Overlay text item uses a monospace font.
- [KNOWN] Existing edge selection replacement behavior remains unchanged.
