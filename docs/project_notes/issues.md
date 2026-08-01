# Work Log (Issues)

This file tracks work history and ticket references.

## Templates

### YYYY-MM-DD - TICKET-ID: Brief Description
- **Status**: Completed / In Progress / Blocked
- **Description**: 1-2 line summary
- **URL**: Link to ticket or PR
- **Notes**: Any important context

## Log

### 2026-08-01 - SETUP-001: Initialize Project Memory
- **Status**: Completed
- **Description**: Created docs/project_notes/ (bugs, decisions, key_facts, issues) and
  wired memory protocols into CLAUDE.md, AGENTS.md, and GEMINI.md.
- **URL**: N/A
- **Notes**: Project is pre-code; next milestone is the v1 ingest spine
  (see `STL_CURATOR_SEED.md` § "First Session Goal").

### 2026-08-01 - SETUP-002: M1 ingest spine implemented
- **Status**: Completed
- **Description**: Full ingest pipeline (scan → hash → mesh facts → grouping →
  thumbnails → vault notes → dup/error reports) implemented and wired end-to-end
  (`uv run stl-curator ingest`). Verified against real data: a 386-file Archvillain
  Games release dropped into `example_stls/` (229 STL, 122 LYS, 29 PNG, 6 JPG).
  Dry-run predictions matched the real run exactly (127 groups, 0 errors, 16
  needs-review); a second real run confirmed full idempotency (`created 0,
  updated 0`).
- **URL**: N/A
- **Notes**: Empirical observations (creator/campaign inference is inverted on
  `Creator - Release/Model/file` layouts; STL_-prefix presupported variants split
  from plain variants into separate model notes due to a fuzzy-match threshold
  miss; thumbnail harvest is folder-scoped so most thumbs ended up GL-rendered
  rather than harvested despite promo PNGs existing) are preserved in
  `docs/project_notes/m1-run-observations.md`; triaged follow-ups in
  `docs/project_notes/m1-followups.md`. Final review added a fix wave
  (human-regrouping claims, divergence-aware rebuild, path-scoped tombstones,
  POSIX-safe long_path) before merge.

## Usage Tips

- Log completed work with a ticket/PR id, date, and link so history stays traceable.
- Keep descriptions to 1-2 lines; put longer context in the **Notes** field.
- Archive entries older than ~3 months by manual cleanup; this log is not automated.
