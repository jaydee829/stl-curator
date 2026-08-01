# M1 Follow-ups (triaged at final review, 2026-08-01)

Deferred items from the M1 branch review, in rough priority order for M1.5.
None block the merge; all were triaged OK-TO-DEFER by the final whole-branch
review (or logged during the fix wave).

## Grouping / vault tuning (informed by the real-corpus run — see m1-run-observations.md)

- **Creator/campaign inference inverts** on `Creator - Release/Model/` layouts
  (fused folder name became the creator; model folders became fake campaigns).
  One pure function (`infer_creator_campaign`), two call sites. M2's MMF
  structure-oracle also corrects this where matches exist.
- **`STL_`/`LYS_` prefix splits** supported/unsupported variants into separate
  notes (~60/127 groups): `normalize_stem` strips trailing tokens only; add
  leading-token stripping + `stl`/`lys` marker vocab.
- **Thumbnail harvest is folder-scoped**: 96/127 thumbs were GL-rendered
  despite promo art existing one level up. Add parent-folder walk-up (also
  subsumes the zip-adjacent-images gap).
- **Caution**: all three change group ids → note filenames. Tune BEFORE any
  hand-curation, then regen vault clean (wipe thumbs dir too — `_ensure_thumb`
  short-circuits on existing dest).

## Known behavioral gaps (logged, not fixed)

- **Rebuild id-miss freeze**: a file added to a model folder but never
  ingested, followed by cache loss + rebuild, restores the note as claimed
  (frozen) and the new file fragments. Needs folder-scoped note-to-machine
  matching in `rebuild_cache` (same insight as the fix-wave's same-folder
  rule).
- **Old cache.db (pre-`member_paths`) fails fast** with
  `sqlite3.OperationalError` on first ingest; `rebuild-cache` is the upgrade
  path. Polish: catch and print "run stl-curator rebuild-cache".
- **Same-folder byte-identical twins** grouped into one note: deleting one of
  the two entries silently converges back to machine truth (no fragments; both
  files really exist). Theoretical corner.
- **Dry-run fidelity**: dry-run skips zip extraction and uses an empty
  in-memory cache, so predictions diverge on stores with un-extracted zips or
  human claims.

## Performance / hygiene

- **mtime/size fast-path unimplemented**: every run re-hashes the full store
  (`Cache.file_unchanged` is dead code). Fine at 386 files; wrong at
  multi-TB. Batch SQLite commits at the same time.
- **Drop `group_max_simple`** config knob (never read; the confidence-collapse
  gate subsumes it).
- **Drop unused `root` param** in `extract_needed_zips`.
- Entity note filenames are unslugged raw folder names (cross-OS edge).
- Thumbnails: RGBA→RGB drops alpha without compositing; report tables don't
  escape `|`/newlines; error report records first path only for dup-hash
  errors.
- Obsidian: `thumb:`/`footprint:` pointers don't resolve as images inside the
  vault (they're store-relative, and cross the vault-repo boundary post
  ADR-002) — decide an M1.5 approach (symlink dir, Obsidian attachment
  folder, or path rewrite at note-write time).
