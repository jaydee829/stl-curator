# Task 15 Report: Wire-up run against example_stls and work log

## Status: DONE

## What was done

1. Created `config.toml` at repo root (gitignored) — identical to `config.example.toml`
   content (paths already pointed at `C:/dev/STL_curator/{example_stls,vault,thumbs,
   footprints,cache.db}`, so no divergence to reconcile):
   ```toml
   store_root = "C:/dev/STL_curator/example_stls"
   vault_dir = "C:/dev/STL_curator/vault"
   thumbs_dir = "C:/dev/STL_curator/thumbs"
   footprints_dir = "C:/dev/STL_curator/footprints"
   cache_db = "C:/dev/STL_curator/cache.db"
   group_max_simple = 6
   group_similarity = 80
   group_confidence_min = 0.6
   ```
2. Ran `uv run stl-curator ingest --config config.toml --dry-run` — completed, no crash.
3. Ran `uv run stl-curator ingest --config config.toml` (real) — completed, no crash,
   wrote `vault/`, `thumbs/`, `cache.db`.
4. Ran it again — verified no-op (`created 0, updated 0`).
5. Inspected vault output, duplicate/error reports, sampled 5 model notes, verified
   `.lys` files are ignored, verified thumbnail harvesting source (`cache.db` `thumbs`
   table cross-checked against summary counts).
6. Updated `docs/project_notes/issues.md` and `docs/project_notes/key_facts.md`.
7. Verified `git status` shows nothing from `vault/`, `config.toml`, `cache.db`,
   `thumbs/` (all correctly gitignored).
8. Committed only the `docs/project_notes/` changes.

## Run summary numbers

| Metric | Dry-run | Real run #1 | Real run #2 (no-op check) |
|---|---|---|---|
| files | 386 | 386 | 386 |
| groups | 127 | 127 | 127 |
| created | 127 | 127 | **0** |
| updated | 0 | 0 | **0** |
| unchanged | 0 | 0 | 127 |
| errors | 0 | 0 | 0 |
| needs_review | 16 | 16 | 16 |
| thumbs_harvested | 31 | 31 | 0 |
| thumbs_rendered | 96 | 96 | 0 |
| thumbs_missing | 0 | 0 | 0 |

Dry-run predictions matched the real run's numbers exactly for files/groups/created/
errors/needs_review — the one caveat is `thumbs_rendered` in dry-run mode is an
**optimistic, unverified count** (the code comment in `pipeline.py::_ensure_thumb`
says so explicitly: "optimistic count; dry-run doesn't probe GL"). In this instance the
real run's GL renders all succeeded too (0 missing both times), so the optimism didn't
bite, but that's not guaranteed in general — a fresh clone-like dry-run cannot actually
prove pyrender/GL will work in real execution.

Acceptance criteria met: second real run reports `created 0, updated 0` (full no-op,
all 127 notes `unchanged`, all thumb counters 0 since `_ensure_thumb` short-circuits
on `dest.exists()`).

`.gitignore` compliance verified — `git status --short` after all three runs shows
**zero output**: `vault/`, `config.toml`, `cache.db`, `thumbs/` never appear.

## OBSERVATIONS

This is the empirically valuable part of M1 — running the real pipeline against a
real, messy release (Archvillain Games — Tome of Demons Volume 1, 386 files: 229 STL,
122 LYS, 29 PNG, 6 JPG, across 9 per-model subfolders, several with `Pose N/`
sub-subfolders) surfaces exactly the kind of naming-convention edge cases synthetic
fixtures would have hidden.

### 1. Creator/campaign inference is systematically wrong for this layout

`infer_creator_campaign()` (`src/stl_curator/vault.py:147`) takes `parts[0]` of the
relative path as **creator** and `parts[1]` (when depth ≥ 3) as **campaign**. The
store layout here is `<Creator+Release fused>/<model folder>/<file>` — there is no
campaign level in the actual folder structure, so:

- **Creator entity**: exactly one was created —
  `vault/creators/Archvillain Games - Tome of Demons Volume 1.md` — using the whole
  fused folder name as the creator identity. This means a *second* Archvillain Games
  release dropped in later (e.g. "Archvillain Games - Tome of Demons Volume 2") would
  mint an entirely separate creator entity rather than aggregating under one
  "Archvillain Games" node. The creator graph node is really "this specific release,"
  not the studio.
- **Campaign entities**: 9 were created, one per model subfolder — e.g.
  `Archvillain Games - Tome of Demons Volume 1 Armaros, Chaos Incarnate.md`,
  `... Decataurs.md`, `... Vulduk.md`, etc. These are **not campaigns** — they're
  individual sculpts/models within the one real campaign (Tome of Demons Vol. 1).
  Semantically this is 100% inverted: the one true campaign got folded into the
  creator string, and the actual model names got promoted to fake "campaign" nodes.
  Every model note's `campaign:` frontmatter field points at one of these
  per-model pseudo-campaigns, e.g. from `armaros.md`:
  ```yaml
  campaign: '[[Archvillain Games - Tome of Demons Volume 1 Armaros, Chaos Incarnate]]'
  creator: '[[Archvillain Games - Tome of Demons Volume 1]]'
  ```
  This is a real gap for any Patreon/MMF-style publisher whose top folder is
  `Creator - Release Name` rather than `Creator/Release/Model` — which appears to be
  the *common* case for this kind of source data, not an edge case. Worth a v1.5
  follow-up: split-on-delimiter heuristic (` - ` is a strong signal here) or a
  config-level per-source override, rather than depth-based inference alone.

### 2. Grouping: the "STL_ prefix problem" is real and inconsistent

Archvillain ships two file families per part — plain (unsupported) and
`STL_..._Supported.stl` (presupported) — plus matching `.lys` (Lychee, ignored).
`normalize_stem()` only strips **trailing** tokens (pose/variant/part/marker suffixes
via a tail-popping loop); it never strips a **leading** `stl_` token. Concretely:

```
"Armaros_Base.stl"              -> stem tokens after stripping "_base" (part) -> core "armaros"
"STL_Armaros_Base_Supported.stl" -> stem tokens after stripping "_supported" (marker),
                                     "_base" (part) -> core "stl_armaros"
```

`fuzz.token_set_ratio("stl_armaros", "armaros")` = **77.8**, just under the configured
`group_similarity = 80` threshold — confirmed by direct measurement
(`rapidfuzz.fuzz.token_set_ratio`). So the supported and unsupported variants of the
**same physical model** end up as two separate model notes:
`archvillain-games-tome-of-demons-volume-1--armaros.md` (unsupported, 5 parts,
`assembly: mixed`) and `...--stl-armaros.md` (supported, 5 parts, `assembly: mixed`,
different `id`, different `height_mm` — 78.4mm vs 122.3mm, i.e. even the *scale*
differs between the two drops, which is itself useful signal these genuinely are
different variants worth separate notes, just not for the reason the tool thinks).
Quoted frontmatter (trimmed):
```yaml
# armaros.md (unsupported)
id: f4908937
assembly: mixed
title: Armaros
height_mm: 78.4313735961914
files: [Armaros_Base.stl (part), Armaros_Body_Wings.stl (part),
        Armaros_Head.stl (part), Armaros_Sword.stl (variant), Armaros_Tail.stl (part)]
```
```yaml
# stl-armaros.md (supported)
id: d263087c
assembly: mixed
title: Stl Armaros
height_mm: 122.32501220703125
files: [STL_Armaros_Base_Supported.stl (part), STL_Armaros_Body_Wings_Supported.stl (part),
        STL_Armaros_Head_Supported.stl (part), STL_Armaros_Sword_Supported.stl (variant),
        STL_Armaros_Tail_Supported.stl (part)]
```
Note the leaked `Stl` prefix in the human-facing `title: Stl Armaros` — cosmetically
ugly and a clear tell of the underlying bug. 60+ of the 127 groups in this run show
the same `stl-*` vs plain split (visible directly in `ls vault/models | grep -i base`,
which returns 17 separate "base" notes across different poses/prefixes for what is
structurally a much smaller number of physical bases).

**Inconsistent edge case found**: `LeftWing`/`RightWing` are camelCase with no
separator, so `normalize_stem`'s `re.split(r"[-. _]+", stem)` never splits them into
`left`+`wing` — `"leftwing"`/`"rightwing"` survive as a single unrecognized token
(not in `part_words`, which only has `wing`/`wings`, not `leftwing`). This causes
`role="model"` misclassification (should be `part`) and, worse, asymmetric grouping:
- `Armaros_RightWing.stl` alone became its own `single`-assembly group
  (`armaros-rightwing.md`, confidence 1.0).
- `Armaros_LeftWing.stl` + `STL_Armaros_LeftWing_supported.stl` +
  `STL_Armaros_RightWing_supported.stl` got fuzzy-clustered together into **one**
  group that fell below `group_confidence_min` and hit the `needs-review` fallback
  path (`archvillain-games-tome-of-demons-volume-1--stl-armaros-rightwing.md`):
  ```yaml
  id: 19bc046d
  assembly: needs-review
  group_confidence: 0.81
  title: Stl Armaros Rightwing
  tags: [needs-review]
  files:
    - Armaros_LeftWing.stl (role: model)
    - STL_Armaros_LeftWing_supported.stl (role: model)
    - STL_Armaros_RightWing_supported.stl (role: model)
  ```
  So the plain right wing split off by itself while the plain left wing got dragged
  into a mixed left/right supported cluster — not wrong exactly (needs-review is the
  honest "I'm not sure" signal, and it did fire), but the *specific* membership is
  arbitrary and a human curator will need to manually split `19bc046d` into left/right
  and merge the correct half with `armaros-rightwing.md`.

### 3. Assembly classification on a genuinely multi-part model works reasonably

For `armaros.md` / `stl-armaros.md` above, `assembly: mixed` is the right call —
the group mixes `part` (Base/Body/Head/Tail) and `variant` (Sword, since "sword" is
in `variant_words`) roles, which is a legitimate mix (this model has an
alternate-weapon variant plus body parts). A clean single-file model like
`Decataurs/Base.stl` correctly got `assembly: single`:
```yaml
# base.md (Decataurs)
id: c8738f48
assembly: single
title: Base
files: [{path: .../Decataurs/Base.stl, role: part}]
```
(role `part` on a single-file group is slightly odd cosmetically but harmless —
`_assembly()` only reads `len(members)==1 -> "single"`, ignoring role.)

### 4. Thumbnail harvest: promo PNGs get used, but only within their own folder

31 harvested / 96 rendered / 0 missing, confirmed against `cache.db`'s `thumbs` table
directly (not just the summary line) — e.g. all 4 sampled Armaros-folder groups
(`f4908937`, `1d4fa396`, `d263087c`, `19bc046d`) show `source='harvested'`, i.e. the
promo PNGs (`ToD1.IndPres.Armaros0{1,2,4} (Large).png`) were correctly picked and
reused across every group that lives directly in the `Armaros, Chaos Incarnate/`
folder. But the brief's expectation that "renders should be rare since promo PNGs
exist" turned out backwards **because grouping is folder-scoped and promo images only
live in the top-level per-model folder** — subfolders like `Outworld Crushers/Pose 2/`
and `Pose 3/` have their own STL groups but *no local images*, so those groups fall
through to real `pyrender` GL rendering. All 96 renders succeeded (0 missing), so GL
offscreen rendering does work correctly on this machine, but the harvest/render ratio
(31:96) is dataset-structure-dependent, not a promo-PNG-coverage question — worth
noting for future write-ups since 76% rendered vs 24% harvested is a very different
mix than "renders should be rare" implied going in. `pick_group_image`'s scoring regex
(`_GOOD`/`_BAD` in `thumbs.py`) never fired on any Archvillain promo filename (no
"render/preview/beauty/box/art/cover/hero" substrings in `ToD1.IndPres.*`), so harvest
selection fell back to plain file-size ranking — which happened to still pick
reasonable images, but is worth flagging as untested-in-practice logic.

### 5. Duplicate report: correctly catches Archvillain's repeated-file-at-multiple-paths pattern

`vault/reports/duplicates.md` found exactly 2 duplicate content groups, both in
`Outworld Crushers/` where the same base STL/LYS is shipped once at the model root and
again inside each `Pose N/` subfolder:
```
| `43624da5` | 3 | .../Outworld Crushers/LYS_Base_Supported.lys <br>
                    .../Outworld Crushers/Pose 2/LYS_Base_Supported.lys <br>
                    .../Outworld Crushers/Pose 3/LYS_Base_Supported.lys |
| `dcbcae4c` | 3 | .../Outworld Crushers/Pose 2/STL_Base_supported.stl <br>
                    .../Outworld Crushers/Pose 3/STL_base_supported.stl <br>
                    .../Outworld Crushers/STL_base_supported.stl |
```
Note the `.lys` duplicate is reported even though `.lys` files never appear in any
model note or grouping pass — the duplicate-hash report operates over *all* cached
files (`cache.duplicate_hashes()`), independent of `kind`, which is correct behavior
(a curator cares about redundant disk usage across any file type, not just STLs).
This also incidentally confirms `.lys` files **are** hashed/cached (needed for dedup)
even though they're excluded from grouping — consistent with `kind="other"` in
`scan.py`'s `_KIND_BY_EXT` map (`.lys` isn't in `IMAGE_EXTS` or `{stl, zip}`, so it
falls to the `"other"` default) and `pipeline.py` only building `by_folder`/
`images_by_folder` from `kind in {"stl", "image"}`.

### 6. Errors: none

`vault/reports/errors.md` reads `# Ingest Errors\n\nNone found.` — all 229 STL files
parsed cleanly through `trimesh` for mesh facts (height/triangles/watertight), and all
96 GL renders succeeded. `errors: 0` in every run summary. No crash, no traceback, no
files needing manual repair.

### 7. `.lys` (Lychee) files: confirmed ignored

Verified by design (`scan.py`'s `_KIND_BY_EXT` maps only `.stl`→stl, `.zip`→zip, image
extensions→image; everything else, including `.lys`, defaults to `kind="other"`) and
empirically (`grep -rl "\.lys" vault/models` returns zero matches — no `.lys` path
appears in any of the 127 model notes' `files:` lists). They're still hashed into
`cache.db` (see duplicate report above) but never grouped, never contribute a role,
and never appear in frontmatter file lists.

### 8. Footprint pointers are generated but never resolve — as designed

Every file entry's frontmatter includes a `footprint:` pointer, e.g.
`footprints/f9/f9df0077....json`, but `footprints_dir` (`C:/dev/STL_curator/
footprints/`) was **never created** — `find footprints -name "*.json"` errors with
"No such file or directory". This is not a bug: the task-15 brief's self-review notes
explicitly list "footprint JSON generation (plate_packer's side)" as deliberately out
of M1 scope. Flagging it here only so a future reader inspecting the vault doesn't
mistake the dangling pointers for a defect — they're forward-references to a
not-yet-built downstream tool.

### 9. Needs-review rate

16 of 127 groups (12.6%) landed in `needs-review` — a reasonable "flag for human"
rate for a first pass against real, inconsistently-named vendor data. Given the
STL_-prefix and camelCase-part-name issues above, the *true* needs-review rate (i.e.
groups a human would actually want to double-check) is arguably higher — several
`assembly: mixed`/`multipart` groups with `group_confidence: 1.0` are quietly wrong
(the split supported/unsupported pairs) without ever being flagged, since confidence
is computed only from within-cluster fuzzy-match agreement, not from cross-cluster
near-misses like the 77.8-vs-80 threshold case above.

## Top 3 observations (one line each)

1. Creator/campaign inference inverts on `Creator - Release/Model/file.stl` layouts — one bogus creator-per-release, and 9 model-folders wrongly promoted to fake "campaign" entities.
2. The STL_-prefix (presupported) vs plain filename pattern splits the *same physical model* into two separate, confidently-scored (1.0) model notes across ~60+ of the 127 groups, because `normalize_stem` only strips trailing tokens and the fuzzy match lands at 77.8 vs an 80 threshold.
3. Thumbnail harvest is folder-scoped, so despite promo PNGs existing per model, 76% of thumbnails (96/127) came from real GL rendering rather than harvest — all renders succeeded (0 missing) confirming pyrender works, but the harvest-first assumption undercounts badly on multi-pose-subfolder releases.
