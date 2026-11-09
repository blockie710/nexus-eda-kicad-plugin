# DRC Violation Data Model

**Module:** `nexus_eda.drc`
**Package:** `src/nexus_eda/drc/`
**Status:** Phase 2 (W5.2 — DRC Agent)

## Purpose

Defines a clear, extensible internal data model for DRC (Design Rule Check)
violations extracted from KiCad's `pcbnew` Python API.  This model
decouples downstream consumers — natural-language summary generation
(`t_de653f69`), UI rendering, rule categorization — from the `pcbnew` API,
which varies significantly between KiCad 6, 7, and 8.

## Architecture

```
src/nexus_eda/drc/
├── __init__.py        # Public API re-exports
├── data_model.py      # Pure-Python data model (no pcbnew dependency)
└── parser.py          # pcbnew adapter (deferred pcbnew import)
```

- **`data_model.py`** is pure Python.  It imports only stdlib modules
  (`dataclasses`, `enum`, `typing`, `datetime`).  It is importable in any
  Python environment — CI, headless scripts, unit tests — without KiCad
  installed.
- **`parser.py`** is the single integration point with `pcbnew`.  The
  `pcbnew` import is deferred (try/except guard) so that importing
  `nexus_eda.drc` never fails when KiCad is absent.  When `pcbnew` is
  unavailable, `parse_pcbnew_drc()` raises `DRCParseError` with a clear
  message.

## Schema

### `Severity` (StrEnum)

| Value    | Meaning                                      |
|----------|----------------------------------------------|
| `error`  | Hard violation — board must not be fabbed    |
| `warning`| Cautionary issue — should be reviewed       |
| `info`   | Advisory — not a violation per se          |
| `none`   | Diagnostic item with no severity            |

### `ViolationType` (StrEnum with registry)

| Enum Member          | Value                  | Category        |
|----------------------|------------------------|-----------------|
| `CLEARANCE`          | `clearance`            | Electrical      |
| `TRACK_WIDTH`        | `track_width`          | Electrical      |
| `VIA_DRILL`          | `via_drill`            | Electrical      |
| `VIA_COVERAGE`       | `via_coverage`         | Electrical      |
| `UNROUTED`           | `unrouted`             | Electrical      |
| `SHORT`              | `short`                | Electrical      |
| `OPEN_CONNECTED`     | `open_connected`       | Electrical      |
| `OVERLAP`            | `overlap`              | Electrical      |
| `DUPLICATE`          | `duplicate`            | Electrical      |
| `MISSING_PIN`        | `missing_pin`          | Electrical      |
| `EXTRA_PIN`          | `extra_pin`            | Electrical      |
| `COMPONENT_PLACEMENT`| `component_placement`  | Component       |
| `COMPONENT_OVERLAP`  | `component_overlap`    | Component       |
| `COMPONENT_CLEARANCE`| `component_clearance`  | Component       |
| `OUT_OF_BOARD`       | `out_of_board`         | Component       |
| `NOT_IN_SCHEMATIC`   | `not_in_schematic`     | Component       |
| `TEXT_OVERLAP`       | `text_overlap`         | Miscellaneous   |
| `ZONE_FILL`          | `zone_fill`            | Miscellaneous   |
| `TRACK_ANGLE`        | `track_angle`          | Miscellaneous   |
| `BOARD_EDGE`         | `board_edge`           | Miscellaneous   |
| `OTHER`              | `other`                | Miscellaneous   |

**Extensibility:** New rule types can be added as enum members (preferred) or
registered at runtime via `ViolationType.register(value, display_name, category)`.
Unknown pcbnew rule ids map to `OTHER`; the original rule id is preserved in
`DRCViolation.raw_rule`.

### `BoardCoordinate` (frozen dataclass)

| Field   | Type             | Unit      | Description                          |
|---------|------------------|-----------|--------------------------------------|
| `x_nm`  | `int`            | nanometers| X position (KiCad internal unit)     |
| `y_nm`  | `int`            | nanometers| Y position (KiCad internal unit)     |
| `layer` | `Optional[str]`  | —         | PCB layer name (e.g. `"F.Cu"`)       |

**Canonical unit:** nanometres (integers).  KiCad uses 10⁻⁶ mm = 1 nm
internally, which avoids floating-point drift on the board grid.

**Convenience properties:**
- `.mm_x`, `.mm_y` — float millimetres
- `.inch_x`, `.inch_y` — float inches
- `.to_mm_tuple()` → `(float, float)`
- `.to_inch_tuple()` → `(float, float)`

**Construction:** `from_nm()`, `from_mm()`, `from_inch()`, `from_dict()`

### `DRCViolation` (frozen dataclass)

| Field             | Type                                              | Required | Default       |
|-------------------|---------------------------------------------------|----------|---------------|
| `violation_type`  | `ViolationType`                                   | yes      | —             |
| `raw_rule`        | `str`                                             | yes      | —             |
| `description`     | `str`                                             | yes      | —             |
| `severity`        | `Severity`                                        | no       | `WARNING`     |
| `coordinate`      | `Optional[BoardCoordinate]`                       | no       | `None`        |
| `bounding_box`    | `Optional[Tuple[BoardCoordinate, BoardCoordinate]]`| no      | `None`        |
| `net`             | `Optional[str]`                                   | no       | `None`        |
| `component`       | `Optional[str]`                                   | no       | `None`        |
| `layer`           | `Optional[str]`                                   | no       | `None`        |
| `module`          | `Optional[Tuple[str, str]]`                       | no       | `None`        |
| `details`         | `Optional[str]`                                   | no       | `None`        |
| `source`          | `str`                                             | no       | `"pcbnew_drc"`|

**JSON serialization:** `to_dict()` / `from_dict()` — full round-trip
including coordinates, bounding boxes, and module tuples.

### `ViolationCollection` (mutable dataclass)

An ordered list of `DRCViolation` instances with filtering and summary
helpers:

- `by_severity(severity)` — filter by `Severity` or string
- `by_type(vtype)` — filter by `ViolationType` or string
- `by_net(net)` — filter by net name
- `by_component(comp)` — filter by component reference
- `by_category(category)` — filter by broad category
- `severity_summary()` → `{"error": N, "warning": N, "info": N}`
- `type_summary()` → `{"clearance": N, "track_width": N, ...}`
- `to_list()`, `from_list()`, `to_dict()` — serialization

### `DRCReport` (mutable dataclass)

Top-level report wrapper:

| Field            | Type                   | Default        |
|------------------|------------------------|----------------|
| `board_file`     | `str`                  | —              |
| `board_title`    | `str`                  | `""`           |
| `run_timestamp`  | `str` (ISO-8601)       | `""`           |
| `source`         | `str`                  | `"pcbnew_drc"` |
| `violations`     | `ViolationCollection`  | empty          |

Derived properties: `total_violations`, `error_count`, `warning_count`,
`info_count`.

## JSON Schema (for IPC / storage)

```jsonc
{
  "board_file": "string",
  "board_title": "string",
  "run_timestamp": "ISO-8601 string",
  "source": "pcbnew_drc",
  "summary": {
    "total": 42,
    "errors": 3,
    "warnings": 7,
    "info": 32
  },
  "violations": [
    {
      "violation_type": "clearance",
      "raw_rule": "clearance",
      "description": "Clearance 0.10mm < 0.15mm minimum",
      "severity": "error",
      "coordinate": {
        "x_nm": 5000000,
        "y_nm": 3000000,
        "layer": "F.Cu"
      },
      "bounding_box": [
        {"x_nm": 1000000, "y_nm": 1000000, "layer": "F.Cu"},
        {"x_nm": 3000000, "y_nm": 2000000, "layer": "F.Cu"}
      ],
      "net": "VCC",
      "component": "R1",
      "layer": "F.Cu",
      "module": ["R1", "front"],
      "details": "Actual: 0.10mm, Required: 0.15mm",
      "source": "pcbnew_drc"
    }
  ]
}
```

## pcbnew Integration (`parser.py`)

### `parse_pcbnew_drc(board_path=None, board=None, ...)`

Loads a KiCad board via `pcbnew.LoadBoard()`, runs `pcbnew.DRC()`, iterates
the violation list, and maps each violation to a `DRCViolation` via
`violation_to_dataclass()`.  Returns a `DRCReport`.

**KiCad version handling:**
- KiCad 7/8: `pcbnew.DRC()` → `drc.SetBoard(board)` → `drc.GetViolations()`
- KiCad 6: `board.GetDesignRulesCheck()` (deprecated/removed in 7+)

### `violation_to_dataclass(pcbnew_violation, source="pcbnew_drc")`

Converts a single pcbnew violation object to `DRCViolation`.  Tolerant of
API differences — tries multiple accessor patterns and falls back gracefully.

### `PCBNEW_AVAILABLE`

Module-level boolean.  `True` when `pcbnew` imported successfully, `False`
otherwise.  Consumers can use this to gate pcbnew-dependent code paths.

## Downstream Consumers

1. **NL Summary Generator** (`t_de653f69`): Consumes `DRCReport.to_dict()`
   via JSON IPC, then calls `ViolationCollection` filter methods
   (`by_severity`, `by_type`, `by_category`) to group violations before
   generating human-readable summaries.

2. **GUI Layer**: Reads `DRCViolation` dataclasses to render violation
   markers on the board canvas — uses `coordinate` for positioning and
   `severity` for color coding.

3. **Rule Categorization**: Future Phase 3 work can use `ViolationType.category`
   and `ViolationCollection.by_category()` to group violations by domain
   (Electrical, Component, Manufacturing).

## Testing

```bash
pytest tests/test_drc_data_model.py -v
```

Tests cover: coordinate construction/conversion, enum mapping, serialization
round-trips, collection filtering, parser adapter, and a full end-to-end
JSON round-trip simulating IPC to the summary generator.
