# STL Library Curator — Project Seed

## Problem Statement

Years of Kickstarter/Patreon/MMF downloads have produced a multi-hundred-GB folder of STLs with no findable structure. Repeated attempts at folder hierarchies have failed because models don't fit a single hierarchy (a model is simultaneously "GoblinCo Patreon 2024-03", "goblin", "32mm", "unpainted", "used in Thornwood campaign"). The fix is a **graph + tag structure**: flat storage, rich metadata, links instead of folders.

Companion project: the resin plate packer (separate seed doc) will eventually consume this library as its model registry.

## Core Design Decisions (settled)

1. **The vault is a generated index, not the storage.** Binaries (STLs, zips, thumbnails) never enter git or the vault. Markdown notes contain relative paths to files on disk. The pipeline writes/updates notes; the human corrects and links.

2. **Filesystem is the source of truth for files; frontmatter is the source of truth for curation.** A SQLite database may cache/join both for fast queries, but it must always be rebuildable from (files on disk + vault frontmatter). No state lives only in SQLite.

3. **Thumbnails: harvest first, render as last resort.** Most downloads already ship renders (promo art in the zip), and MMF serves images by URL — using these saves significant compute and they're usually *better* than a raw mesh render. Priority order: (1) image found in the model's folder/zip, (2) MMF object image, (3) own pyrender render as fallback for the truly art-less. All normalized to small webp, stored content-addressed by STL hash (`thumbs/ab/abcd1234….webp`), outside git. Still cache-tier: harvested images are re-extractable/re-downloadable, renders regenerable.

4. **Zero new cloud spend.** Backup = `rclone sync` to existing Google Drive or OneDrive. Vault = private GitHub repo. No GCP.

5. **MMF API is an enrichment source and a library-sync source, never a core dependency.** Everything must work for models with no MMF match (most Patreon/KS content). But the curator should also see the *other* direction: MMF holdings that aren't in the local store yet ("owned-not-downloaded"), with optional fetch. Scraping-with-session-cookie tools, if ever built, are quarantined optional helpers.

6. **Files are normalized on intake.** Filename cleanup (strip `#`, `%`, weird unicode, absurd path lengths — Kickstarter zips are full of them) happens once at ingest. This is required anyway for OneDrive compatibility and sane tooling.

## Architecture

```
STL store (local disk, flat-ish, normalized names)
  │  scan/hash
  ▼
Ingest pipeline ──renders──▶ thumbnails (content-addressed, local)
  │        └──enriches──▶ MMF API (optional, per-object)
  │        └──auto-tags──▶ LLM (geometry stats + folder/filename context)
  ▼
Obsidian vault (markdown + YAML frontmatter)  ←— human curation happens here
  │
  ├─▶ git (vault text only, private repo)
  ├─▶ SQLite cache (rebuildable; fast queries; future packer integration)
  └─▶ rclone → Google Drive / OneDrive (STLs + thumbnails, scheduled)
```

## Vault Design

- **One note per model** (or per kit where files are inseparable), auto-generated, e.g. `models/goblinco--owlbear-large.md`.
- **Entity notes** for creators, campaigns/releases, and projects: `creators/GoblinCo.md`, `campaigns/GoblinCo 2024-03.md`, `projects/Thornwood Campaign.md`. Wikilinks connect model → creator → campaign → project.
- **Frontmatter schema (v1):**
  ```yaml
  id: abcd1234          # content hash prefix, stable key
  paths: [ ... ]         # relative paths to STL(s)/zip
  thumb: thumbs/ab/abcd1234.webp
  creator: "[[GoblinCo]]"
  campaign: "[[GoblinCo 2024-03]]"
  source: patreon | kickstarter | mmf | other
  mmf_id: 123456        # optional
  tags: [monster, goblinoid, 32mm, supported]
  scale: 32mm
  base: 50mm-round
  supported: true
  status: unprinted | printed | painted
  height_mm: 48.2       # from mesh
  ```
- **Queries** via Dataview or Obsidian Bases ("all unpainted 32mm monsters", "everything from creator X not yet printed"). Because it's all plain markdown, external tooling (ChromaDB RAG, the packer, scripts) reads the same data.
- **Human/machine boundary:** pipeline owns file facts (paths, hash, dimensions, thumb); human owns curation fields (status, project links, tag corrections). Re-runs must never clobber human edits — merge frontmatter, don't rewrite notes.

## Ingest Pipeline (Python)

1. **Scan & hash**: walk the store, hash file contents; hash = identity (survives renames/moves; detects duplicates across kickstarter re-releases — dedup reporting is a free win).
2. **Normalize**: fix filenames/paths on first ingest (see decision 6).
3. **Extract mesh facts**: trimesh — bounding box, height, watertightness, triangle count. Cheap and useful for scale inference and packer prep.
4. **Acquire thumbnail (harvest-first)**:
   a. Scan the model's folder/zip for existing images; pick the best candidate by heuristic (largest resolution, filename hints like `render`/`preview`/box-art patterns; penalize `supports`, `instructions`, `assembly`). Ambiguous cases can be settled later by the vision LLM in the tagging pass at zero extra cost.
   b. Else use the MMF object image if a match exists (store the URL in frontmatter too, so it's re-fetchable).
   c. Else render: trimesh/pyrender offscreen, fixed camera (¾ view), fixed lighting — deterministic so re-renders are no-ops. Expected to be the minority path.
   All paths normalize to webp at the content-addressed location.
5. **Enrich (optional per model)**: MMF lookup where a match exists.
6. **Auto-tag**: LLM given folder path, filenames, mesh stats, MMF metadata if present, and the rendered thumbnail (vision) → proposes tags/scale/type. Confidence-gated: low-confidence tags land in a `needs-review` state rather than silently polluting the taxonomy.
7. **Write/merge vault notes** + update SQLite cache.

Idempotent by design: re-running over the whole store is safe and is the normal mode of operation (mirrors the triage-ledger pattern from Shelfwright's Gmail pipeline).

## MMF API Integration (verified against their OpenAPI spec)

- Real documented API: OAuth2, API clients created in MMF account settings. Spec: github.com/MyMiniFactory/api-documentation (`myminifactory-api.yaml`).
- **Available and useful**: `/search`; `/objects/{id}` (name, description, printing details, dimensions, designer, **tags**, **categories**, **images**); `/objects/{id}/files` (filenames → diff against local holdings to verify completeness); `archive_download_url` on objects (OAuth-connected users only) for sanctioned file fetching; `/users/{username}/collections`.
- **Not available: any "my purchases" endpoint.** The API cannot enumerate what you own. Bridges, in order of preference:
  1. Maintain MMF collections as the ownership index (collections are API-readable).
  2. Fuzzy-match local folder/zip names against `/search`; flag unmatched for manual linking.
  3. (Quarantined, optional, brittle) session-cookie scrape of the library page.
- Respect their guidelines: attribute/link back to object pages; don't rebuild their platform.

### Library Sync (owned-not-downloaded)

The curator should surface MMF holdings absent from the local store, not just enrich what's already there:

1. Enumerate ownership via the best available bridge (collections first; see above).
2. Diff against local holdings by `mmf_id` and fuzzy name match.
3. Missing objects get a **stub vault note** (`status: not-downloaded`) with MMF metadata, thumbnail from MMF's image URL, and a link to the object page — so the library view is complete even where the files aren't.
4. Optional `fetch` command: download via `archive_download_url` into the store, at which point normal ingest takes over and upgrades the stub.
5. **Verify early:** confirm `archive_download_url` actually works for *purchased paid* objects under a user OAuth token (the spec says OAuth-connected-user only; whether purchase entitlements flow through needs a live test). If it doesn't, library sync still works — fetch just degrades to "open the object page in a browser."

## Backup Strategy

- `rclone sync <store> <remote>:stl-backup` on a schedule (Task Scheduler/cron). Remote = Google Drive or OneDrive, whichever has headroom.
- **Always** use `--backup-dir <remote>:stl-trash/$(date +%F)` — sync mirrors deletions, and this converts them into recoverable moves. This is the difference between a backup and a replication of mistakes.
- Initial upload of a large store: throttle (`--transfers 4`, modest `--tpslimit`) to dodge Drive 403s; expect it to take a while.
- Do **not** put the store or vault inside Drive/OneDrive desktop-client sync folders (client mirroring fights git and chokes on huge file counts). rclone only.
- Vault: plain git, private GitHub repo. Thumbnails ride the rclone sync, not git/LFS.

## Tech Stack

- Python 3.11+; `trimesh` + `pyrender` (offscreen thumbnails), `numpy`, `httpx` (MMF), `pyyaml`/`python-frontmatter` (note read/merge), `sqlite3`, `rapidfuzz` (name matching), `typer` CLI
- LLM calls for tagging: provider-abstracted (same pattern as Shelfwright) — Claude or Gemini, vision-capable
- Tests: `pytest`. Priorities: frontmatter merge never clobbers human fields; hashing/identity stability; thumbnail determinism; ingest idempotency.

## Roadmap

- **v1:** scan/hash/normalize → mesh facts → thumbnails → generated vault (models + creators auto-detected from folder structure) → duplicate report. No MMF, no LLM. *This alone beats the status quo.*
- **v1.5:** LLM auto-tagging with review queue; Dataview/Bases dashboards (by status, by creator, untagged queue).
- **v2:** MMF enrichment + completeness verification; **library sync with stub notes and optional fetch**; project notes and campaign linking; rclone backup automation.
- **v3:** packer integration (vault as model registry: pick models in Obsidian → emit a pack job); print/paint status workflows; maybe supported/unsupported variant linking.

## Open Questions (resolve empirically, early)

1. **Auto-tag quality is the whole ballgame.** Run the tagging prompt against ~30 known models (thumbnail + path context) and score it before building the review UX around it. If vision tagging is mediocre, folder-path heuristics may carry more weight than expected.
2. Kit granularity: when is a zip one note vs. many? (Terrain sets vs. single minis.) Probably: one note per zip by default, split on demand.
3. How well does the image-harvest heuristic pick the right art from real zips? (Sample across a few creators — naming conventions vary wildly.) What fraction of the library actually needs the pyrender fallback? If small, pyrender's Windows finickiness (EGL/OSMesa) stops mattering; if large, verify it early or fall back to trimesh's built-in save_image.
3b. Does `archive_download_url` honor purchase entitlements under user OAuth? (Live test with one owned paid object.)
4. Fuzzy-match precision for MMF linking — what threshold avoids false positives on generic names ("Goblin Archer")?
5. Vault scale: does Obsidian stay snappy at 5–10k model notes? (Reports say yes with Bases; verify before committing to per-model notes for true bulk items.)

## First Session Goal

Build the v1 spine end-to-end on a *subset* (one creator's folder, ~50–100 models): scan → hash → mesh facts → harvest thumbnails (render only where nothing harvestable) → generate vault notes → open in Obsidian and browse. Answers open questions 3 and 5 immediately, and produces the corpus for the tagging experiment (question 1) next session.
