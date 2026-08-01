# Architectural Decision Records

This file documents key architectural decisions, their context, and trade-offs.

## Templates

### ADR-XXX: Decision Title (YYYY-MM-DD)

**Context:**
- Why the decision was needed
- What problem it solves

**Decision:**
- What was chosen

**Alternatives Considered:**
- Option 1 -> Why rejected
- Option 2 -> Why rejected

**Consequences:**
- Benefits
- Trade-offs

## Decisions

### ADR-000: Founding Design Decisions (2026-08-01)

The project's nine founding decisions (graph+tag vault over folder hierarchy,
vault-as-generated-index, filesystem/frontmatter as dual sources of truth,
content-hash identity, harvest-first thumbnails, idempotent ingest, MMF as
optional enrichment, zero new cloud spend, normalize-at-intake) are recorded in
`STL_CURATOR_SEED.md` § "Core Design Decisions" and summarized in `CLAUDE.md`.
They are settled — a superseding ADR here is required to change any of them.
New decisions start at ADR-001.

### ADR-001: Toolchain — uv, ruff, GitHub, Obsidian (2026-08-01)

**Context:**
- Greenfield Python project needs settled dev tooling before scaffolding.

**Decision:**
- `uv` for package/env management (single lockfile, `uv run` for all commands).
- `ruff` for lint + format, pinned as a uv dev dependency (no global install).
- GitHub (private repo, `gh` CLI available) for the vault and source hosting.
- Obsidian as the vault front-end (Dataview/Bases for queries).

**Alternatives Considered:**
- pip + venv + black/flake8 -> more tools, slower, no lockfile story.
- Poetry -> heavier, uv is faster and already installed.

**Consequences:**
- All commands run through `uv run`; contributors need uv installed.
- One formatter/linter (ruff) keeps config to a single `pyproject.toml` section.

<!--
Add new ADRs below. Number them sequentially (ADR-002, ADR-003, ...).
Never delete an ADR — if a decision changes, add a revision note with the new date
and, if needed, a superseding ADR that references the old one.
-->

## Usage Tips

- Check this file **before** proposing an architectural change. If the proposal
  conflicts with an existing ADR, acknowledge the prior decision and explain why
  revisiting it is warranted.
- ADRs are lightweight and historical — keep all of them.
- Find decisions about a topic with
  `Grep(pattern="^### ADR-", path="docs/project_notes/decisions.md")` or a keyword search.
