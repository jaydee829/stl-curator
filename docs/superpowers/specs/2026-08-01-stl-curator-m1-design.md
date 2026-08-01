# STL Curator — Milestone 1 Design (Local Spine, MMF-Aware)

Date: 2026-08-01
Status: Approved in brainstorming session (this doc is the written record)
Supersedes nothing; extends `STL_CURATOR_SEED.md` with decisions made 2026-08-01.

## 1. Scope

Milestone 1 builds the local-only ingest spine, run against `example_stls/`:

scan → hash → group → mesh facts → thumbnails (harvest-first) → generate vault → duplicate report

MMF-aware but MMF-free: the schema reserves MMF fields and the design anticipates
matching, but no API code is written. Deliverable: a browsable Obsidian vault over
the sample corpus, plus a duplicate report.

### Decisions made in this session (beyond the seed doc)

- **MMF is a primary organizer, not just enrichment** (many Kickstarters/Patreons
  fulfill on MMF). Priorities when a match exists: (b) grouping/structure,
  (c) taxonomy, (d) completeness. Canonical *file* renaming (a) is deferred:
  local filenames stay untouched on disk; MMF names will title vault notes.
- **Ownership bridge** (milestone 2): one-time session-cookie scrape of the MMF
  "My Library" pages → local `mmf_library.json` ownership index (quarantined
  helper; MMF's API has no purchases endpoint — verified against their OpenAPI
  spec 2026-08-01). Ongoing matching = fuzzy name search validated against that
  index; auto-confirm on owned hits, review queue otherwise. Collections optional.
- **Milestone split**: walk before run. M1 = local spine (this doc). M2 = MMF
  (scrape, match, retitle, tags, completeness). M3+ = per seed doc roadmap.
- **Kit granularity**: heuristic grouping (folder-first + stem clustering),
  with roles distinguishing warband-style variants from split-model parts.
- **Vault colocation now, split later**: vault lives in this repo but must remain
  trivially extractable (see §2).

## 2. Repository Layout

```
STL_curator/                  # this repo (private GitHub)
├── pyproject.toml            # uv-managed; ruff + pytest config
├── config.example.toml       # committed template; real config.toml gitignored
├── src/stl_curator/          # cli.py, scan.py, grouping.py, meshfacts.py,
│                             #   thumbs.py, vault.py, cache.py, config.py
├── tests/
├── docs/                     # project notes, specs (this file)
├── example_stls/             # sample corpus (contents gitignored — binaries)
└── vault/                    # generated Obsidian vault — SELF-CONTAINED
    ├── models/               # one note per model group
    ├── creators/
    ├── campaigns/
    ├── reports/              # duplicates.md, errors.md (generated)
    └── .obsidian/            # committed minimal config (Dataview/Bases)
```

**Split-readiness rules** (the vault will move to its own repo sooner rather
than later):

- Everything under `vault/` uses only vault-internal wikilinks and
  vault-root-relative references.
- Code takes the vault location from config (`vault_dir`); no hardcoded
  relative paths.
- Nothing outside `vault/` links into it.
- Split procedure when the day comes: move directory, `git init`, change one
  config value.

**Outside git entirely**: the real STL store, `example_stls/` contents,
`thumbs/`, `footprints/`, SQLite cache, `config.toml`, `mmf_library.json` (M2).

## 3. Vault Data Model

### Entity notes (creators, campaigns)

Lightweight: identity frontmatter + embedded Dataview/Bases queries that list
linked models/campaigns dynamically. The pipeline never rewrites entity-note
body text — generated content is frontmatter; queries keep lists current;
human prose is safe. Entity stubs are auto-created from the folder convention
`Creator/Release/...` (top two levels) when missing.

### Model note frontmatter (schema v1.1)

```yaml
id: g7f3a2c1              # hash of sorted member-file hashes (group identity)
type: model
title: "Owlbear, Large"    # local-derived in M1; MMF name takes over in M2
creator: "[[GoblinCo]]"
campaign: "[[GoblinCo 2024-03]]"
files:
  - path: "Goblinco/2024-03/owlbear_body.stl"   # relative to store root
    hash: ab12…
    role: part             # part | variant | model | support | unknown
    footprint: footprints/ab/ab12….json          # reserved for plate_packer
assembly: multipart        # multipart | variants | single | mixed | needs-review
thumb: thumbs/g7/g7f3a2c1.webp
thumbs_all: []             # collated variant thumbnails when harvested
height_mm: 122.4           # tallest member; assembled height unknowable in M1
group_confidence: 0.87
tags: [needs-review]       # taxonomy arrives with MMF (M2) / LLM (later)
status: unprinted          # unprinted | printed | painted
source: patreon            # inferred from folder conventions where possible
mmf_id:                    # reserved, empty until M2
paths_root: "D:/STL_store" # config echo; keeps paths relative + portable
```

### Ownership boundary (merge rule)

- **Pipeline owns**: `id`, `files[].hash`, `thumb`, `thumbs_all`, `height_mm`,
  `group_confidence`, `mesh_error`, `paths_root`.
- **Human owns**: `status`, `tags`, `title`, `creator`/`campaign` corrections,
  `files[].role`, `assembly`, and group membership itself.
- Re-runs merge frontmatter field-by-field per this table; human-added unknown
  fields pass through untouched; body text below frontmatter is never
  regenerated once a note exists.
- If a human moves a file entry between notes, the grouping is authoritative:
  those hashes are marked human-claimed in the cache and never regrouped.

### Identity

Group `id` = hash of the sorted member-file hashes. Invariant under file order
and path moves; changes only when membership changes. Note filename is stable
once created (identity follows the note; membership is editable frontmatter).

## 4. plate_packer Interface Contract

This section is the normative interface between STL_curator and the
plate_packer project (in parallel development). Changes require updating both
projects and this section.

**Purpose**: packer consumes the library as its model registry and produces
per-STL packing geometry ("footprints"); the curator surfaces their existence.

**Contract:**

1. **Keying**: everything is keyed by STL content hash (the same hash the
   curator computes at scan time — SHA-256, hex; the first 8 chars form the
   id prefix used in paths). Hash-keying makes the linkage survive file
   renames, moves, and regrouping with zero coordination.
2. **Location**: content-addressed under a shared `footprints_dir`
   (config value in both projects, default sibling of `thumbs/`):
   `footprints/<first-2-hex>/<full-hash>.json`.
3. **Cardinality**: one STL → one JSON document → **many footprints**. The
   packer will produce multiple z-slices per STL for 3D packing; all slices
   live inside the single per-hash document. If the packer later needs
   per-slice files, it owns a per-hash *directory* instead
   (`footprints/<h2>/<hash>/`), and the curator pointer becomes that
   directory. Either way the curator derives the location from the hash.
4. **Schema ownership**: the JSON internals (slice format, polygon encoding,
   versioning) are owned and versioned by plate_packer. The curator treats
   the document as opaque — it records existence (`files[].footprint`) and
   never parses contents.
5. **Write ownership**: `files[].footprint` is a machine-owned frontmatter
   field. The packer (or a curator sync step) may set/refresh it without
   engaging the human-field merge rule.
6. **Durability class**: footprints are cache-tier — regenerable from meshes,
   excluded from git, included in rclone backup alongside thumbnails.
7. **Future (v3, non-normative)**: pack-job flow — human selects models in
   Obsidian (tag or list), curator emits a pack job (list of hashes +
   quantities) for the packer to consume. Out of scope for M1/M2; noted so
   neither project designs against it.

## 5. Ingest Pipeline

Idempotent stages behind a `typer` CLI: `stl-curator ingest <root>`.

1. **Scan & hash** — walk root; SHA-256 every STL/zip/image; inventory in
   SQLite (hash, path, size, mtime). Unchanged hash+path skips downstream
   stages.
2. **Zip handling** — inventory zips; extract to a working area only if not
   already extracted alongside (creators often ship both); the extracted tree
   is what gets grouped; originals never deleted.
3. **Group** — per leaf folder:
   - Few STLs (≤ ~6) with high stem similarity → one group.
   - Else normalize names (lowercase, strip separators), strip suffix
     vocabulary, cluster remaining stems with rapidfuzz token-set similarity.
   - Suffix vocabulary lives in `grouping_vocab.toml` (data, not code) with
     categories that also classify roles:
     poses/loadout (`pose1`, `_a/_b`, trailing `sword`/`helmet`) → `variant`;
     parts (`body`, `head`, `wing_l`, `part01`, `top/bottom/left/right`) →
     `part`; print-prep (`supported`, `presup`, `hollow`) → same-model marker;
     scale (`32mm`, `x1.5`) → same-model marker.
   - Role mix determines `assembly` (variants/multipart/mixed/single).
   - Confidence from cluster tightness; below threshold → keep the group
     coarse (whole folder, one note), `assembly: needs-review`. Never guess
     fine-grained.
4. **Mesh facts** — trimesh per STL: bbox, height, triangle count,
   watertightness. Cached by hash.
5. **Thumbnails** — harvest-first per group: best image in the group's
   folder/zip by resolution + filename heuristics (`render`/`preview`/box-art
   patterns up; `support`/`assembly`/`instruction` down). pyrender offscreen
   fallback (fixed ¾ camera, fixed lighting — deterministic) only when nothing
   harvestable. All normalized to webp at `thumbs/<h2>/<hash>.webp`.
6. **Vault write** — merge-aware note generation per §3; entity stubs created
   as needed.
7. **Duplicate report** — same hash at multiple paths →
   `vault/reports/duplicates.md`.

## 6. Configuration, Cache, Error Handling

- **Config**: `config.toml` at repo root (gitignored; `config.example.toml`
  committed): `store_root`, `vault_dir`, `thumbs_dir`, `footprints_dir`,
  `cache_db`, grouping thresholds. CLI flags override.
- **SQLite cache**: files (hash, path, size, mtime, mesh facts), groups
  (id, members, confidence, human-claimed flag), thumbs (hash → source:
  harvested/rendered/missing). Fully rebuildable:
  `stl-curator rebuild-cache` re-derives everything from disk + vault
  frontmatter. No state lives only in SQLite (founding decision 2).
- **Errors never halt ingest**: corrupt STL → note still written with
  `mesh_error: true`, logged to `vault/reports/errors.md`; unreadable zip →
  flagged, skipped. Pathological Kickstarter paths handled with long-path-aware
  I/O (`\\?\` prefix on Windows); no renaming in M1.
- **Run summary**: N files / groups / notes written / errors / needs-review.
- **`--dry-run`** prints intended changes; an immediate second real run must
  be a no-op (acceptance test).

## 7. Testing

Parametrized pytest suites (each case an atomic named test):

1. **Merge never clobbers human fields** — (existing note, pipeline data,
   expected) tables: human status/tags/roles/regrouping survive; machine
   fields update; unknown human fields pass through; body text untouched.
2. **Grouping heuristic** — (file list → expected groups, roles, assembly)
   tables: goblin-pose variants, split-dragon parts, mixed kit, flat messy
   zip, pre-supported duplicates. Cases sourced from real `example_stls/`
   names once files land; vocab tuning updates the table, not the code.
3. **Identity stability** — group id invariant under order/moves; changes on
   membership change only.
4. **Thumbnail determinism** — same mesh → byte-identical render; harvest
   heuristic picks expected image from synthetic fixtures.
5. **Idempotency** — double ingest over a fixture tree; second run is a no-op.

Fixtures: tiny synthetic meshes generated in-fixture by trimesh (no binaries
in git) + name-only fixtures for grouping tests.

## 8. Milestone 2 Preview (designed-for, not built)

Scrape bootstrap (`mmf_library.json`) → fuzzy match local groups against
owned objects (rapidfuzz against index first, `/search` for the rest;
auto-confirm owned hits, review queue otherwise) → MMF name becomes note
`title` (merge rule: human title edits win) → MMF tags/categories seed
taxonomy → `/objects/{id}/files` diff for completeness. File renaming on
disk remains deferred beyond M2.

**MMF as structure oracle (added 2026-08-01 after the M1 real-data run).**
MMF data disambiguates all three hierarchy levels, directly addressing the
M1 empirical findings (task-15 report):

- *Creator*: object `designer` is authoritative. One confirmed match inside
  a fused folder like "Archvillain Games - Tome of Demons Volume 1" fixes
  the creator entity; the folder-name residue is the campaign.
- *Campaign*: the library/ownership index is purchase-granular, and an MMF
  purchase IS the release bundle — campaigns come from the index with MMF's
  own naming.
- *Model/grouping*: `/objects/{id}/files` listings are authoritative merge
  evidence — files listed under one object belong in one note (repairs the
  `STL_`-prefix supported/unsupported split without vocab tuning), and
  object granularity answers kit-vs-model.

Precedence: filename/folder heuristics remain the offline first pass and
the only path for unmatched (non-MMF) content; MMF-confirmed structure
overrides heuristic guesses but never human corrections (merge rule
unchanged). MMF object images additionally join the thumbnail harvest
chain (priority 2, per seed doc).

## 9. Resolved / Deferred Questions

- Kit granularity: heuristic grouping with roles (resolved; tuning empirical).
- Ownership enumeration: library scrape bootstrap (resolved).
- pyrender-on-Windows risk: bounded — harvest-first should make renders the
  minority path; if pyrender proves unusable, fall back to trimesh
  `save_image` (deferred to implementation; raise as a problem brief if both
  fail).
- Obsidian scale (5–10k notes): answered empirically by M1 vault (deferred).
- Auto-tag quality experiment: after M1 produces the corpus (deferred).
