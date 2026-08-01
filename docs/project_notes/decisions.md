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

### ADR-002: Public code repo; vault split out immediately as private repo (2026-08-01)

**Context:**
- User wants the code repo public. The vault's generated notes catalog owned
  paid content (titles, creators, file manifests) — personal data that also
  exposes paid-release contents; and git history is permanent once public.

**Decision:**
- Code repo (this repo) → public GitHub. `vault/` is gitignored here and
  becomes its own **private** repo from day one (accelerates the planned
  split; supersedes the M1 spec §2's "colocated now, split later").
- Secrets/binaries remain gitignored as before (config.toml,
  mmf_library.json, caches, STLs, thumbs, footprints).

**Alternatives Considered:**
- Private monorepo, split later -> delays public availability; risks vault
  history landing in a repo that later flips public.

**Consequences:**
- Vault gets its own git lifecycle (init on first generation); code repo
  carries only tool + specs + project notes.
- Spec §2 split-readiness rules now apply from day one (they already held).

<!--
Add new ADRs below. Number them sequentially (ADR-003, ADR-004, ...).
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
