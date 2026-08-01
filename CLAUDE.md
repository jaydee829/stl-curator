# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project State

Greenfield. There is no code yet — the entire design lives in `STL_CURATOR_SEED.md`. Read it before doing anything; it contains settled decisions, the roadmap, and open questions to resolve empirically. `example_stls/` is a (currently empty) staging area for sample models to test against.

The first milestone (v1) is the ingest spine end-to-end on a small subset: scan → hash → normalize → mesh facts → harvest/render thumbnails → generate Obsidian vault notes → duplicate report. No MMF integration, no LLM tagging until v1 works.

## What This Is

A curator for a multi-hundred-GB local library of 3D-printable STLs. Instead of folder hierarchies (which failed — models belong to many taxonomies at once), it uses flat storage plus a generated Obsidian vault of markdown notes with YAML frontmatter, wikilinked into a graph (model → creator → campaign → project), backed by a rebuildable SQLite cache.

## Non-Negotiable Design Decisions

These are settled in the seed doc; do not re-litigate them:

1. **The vault is a generated index, not storage.** Binaries (STLs, zips, thumbnails) never enter git or the vault — notes hold relative paths to files on disk.
2. **Sources of truth:** filesystem for file facts, frontmatter for curation. SQLite is a cache and must always be rebuildable from those two; no state lives only in SQLite.
3. **Human/machine boundary:** the pipeline owns file facts (paths, hash, dimensions, thumb); the human owns curation fields (status, project links, tag corrections). Re-runs must merge frontmatter — never rewrite notes or clobber human edits.
4. **Identity = content hash.** It survives renames/moves and powers dedup. Thumbnails are content-addressed by STL hash (`thumbs/ab/abcd1234….webp`).
5. **Thumbnails: harvest first, render last.** Prefer images shipped in the model's folder/zip, then MMF's image URL, then a deterministic pyrender render as the fallback of last resort.
6. **Idempotency is the normal mode.** Re-running ingest over the whole store must be safe; deterministic renders make re-renders no-ops.
7. **MMF API is optional enrichment, never a core dependency.** Everything must work for models with no MMF match. Session-cookie scraping tools, if ever built, are quarantined optional helpers.
8. **Zero new cloud spend.** Backup is `rclone sync` to existing Google Drive/OneDrive (always with `--backup-dir`); vault is a private GitHub repo. No GCP.
9. **Filenames are normalized once at intake** (strip `#`, `%`, weird unicode, absurd path lengths) for OneDrive compatibility and sane tooling.

## Tech Stack (planned)

Python 3.11+, `typer` CLI, `trimesh` + `pyrender` (offscreen renders), `httpx` (MMF API), `python-frontmatter`/`pyyaml` (note read/merge), `sqlite3`, `rapidfuzz` (fuzzy MMF matching), `pytest`. LLM tagging (v1.5) is provider-abstracted (Claude or Gemini, vision-capable) and confidence-gated into a `needs-review` state.

## Toolchain and Commands

Dev tooling is settled (ADR-001 in `docs/project_notes/decisions.md`): **uv** for env/deps, **ruff** for lint+format (dev dependency, not global), **GitHub** for hosting (`gh` CLI available), **Obsidian** as the vault front-end.

Everything runs through uv:

```
uv sync                  # install/update environment from lockfile
uv run pytest            # run tests
uv run pytest tests/test_x.py::test_name   # run a single test
uv run ruff check        # lint
uv run ruff format       # format
```

(Package skeleton doesn't exist yet — update these if the layout diverges once scaffolded.)

## Testing Priorities

From the seed doc, the behaviors that matter most: frontmatter merge never clobbers human fields; hash/identity stability; thumbnail determinism; ingest idempotency.

## Project Memory System

This project maintains institutional knowledge in `docs/project_notes/` for consistency across sessions:

- **bugs.md** — bug log with dates, root causes, solutions, prevention notes
- **decisions.md** — Architectural Decision Records; ADR-000 anchors the founding decisions to the seed doc
- **key_facts.md** — project configuration, conventions, external-service details (never secrets)
- **issues.md** — work log with dates and descriptions

Protocols:

- **Before proposing architectural changes**: check `decisions.md`. The seed-doc decisions are ADR-000 and require a superseding ADR to change. If a proposal conflicts with an existing ADR, acknowledge it and justify revisiting.
- **When hitting errors or bugs**: search `bugs.md` for prior solutions first; document new recurring/instructive bugs when resolved.
- **When looking up configuration**: prefer `key_facts.md` over assumptions.
- **When completing a work session**: log it in `issues.md` (date, brief description, status).
- Style: bullet lists over tables, concise entries (1–3 lines), always dated. Cleanup is manual.

## Key References

- Frontmatter schema v1 and vault layout: "Vault Design" section of the seed doc.
- MMF API spec: github.com/MyMiniFactory/api-documentation (`myminifactory-api.yaml`). Note: there is **no** "my purchases" endpoint — ownership is bridged via API-readable collections, fuzzy name matching, or (quarantined) scraping.
- Pyrender on Windows is known to be finicky (EGL/OSMesa); if the harvest heuristic covers most models, this may not matter — verify early, with `trimesh`'s built-in `save_image` as fallback.
