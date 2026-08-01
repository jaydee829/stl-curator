import zipfile

import frontmatter
import pytest
import trimesh

from stl_curator.cache import Cache
from stl_curator.config import Config
from stl_curator.pipeline import ingest, rebuild_cache


@pytest.fixture
def store(tmp_path) -> Config:
    root = tmp_path / "store"
    kit = root / "GoblinCo" / "2024-03"
    kit.mkdir(parents=True)
    trimesh.creation.box(extents=[5, 5, 30]).export(kit / "goblin_pose1.stl")
    trimesh.creation.box(extents=[5, 5, 31]).export(kit / "goblin_pose2.stl")
    trimesh.creation.box(extents=[20, 20, 80]).export(kit / "troll_king.stl")
    (kit / "render_preview.png").write_bytes(_png_bytes())
    # a zip that needs extraction
    with zipfile.ZipFile(root / "GoblinCo" / "extra.zip", "w") as z:
        z.writestr("owlbear.stl", trimesh.creation.box(extents=[9, 9, 9]).export(file_type="stl"))
    # a duplicate
    (root / "GoblinCo" / "2024-03" / "troll_king_copy.stl").write_bytes(
        (kit / "troll_king.stl").read_bytes()
    )
    return Config(
        store_root=root,
        vault_dir=tmp_path / "vault",
        thumbs_dir=tmp_path / "thumbs",
        footprints_dir=tmp_path / "footprints",
        cache_db=tmp_path / "cache.db",
    )


def _png_bytes():
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "blue").save(buf, "PNG")
    return buf.getvalue()


def test_ingest_creates_vault(store):
    s = ingest(store)
    assert s.created > 0 and s.errors == 0
    models = list((store.vault_dir / "models").glob("*.md"))
    assert models
    assert (store.vault_dir / "creators" / "GoblinCo.md").exists()
    assert (store.vault_dir / "reports" / "duplicates.md").exists()


def test_zip_extracted_and_ingested(store):
    ingest(store)
    assert (store.store_root / "GoblinCo" / "extra" / "owlbear.stl").exists()
    assert any("owlbear" in p.name for p in (store.vault_dir / "models").glob("*.md"))


def test_duplicate_detected(store):
    ingest(store)
    text = (store.vault_dir / "reports" / "duplicates.md").read_text(encoding="utf-8")
    assert "troll_king" in text and "troll_king_copy" in text


def test_second_run_is_noop(store):
    ingest(store)
    s2 = ingest(store)
    assert (s2.created, s2.updated) == (0, 0)
    assert s2.unchanged > 0


def test_dry_run_writes_nothing(store):
    s = ingest(store, dry_run=True)
    assert s.created > 0
    assert not store.vault_dir.exists()


def test_human_edit_survives_rerun(store):
    ingest(store)
    note = next((store.vault_dir / "models").glob("*troll*.md"))
    post = frontmatter.load(note)
    post["status"] = "painted"
    with open(note, "w", encoding="utf-8") as f:
        frontmatter.dump(post, f)
    ingest(store)
    assert frontmatter.load(note)["status"] == "painted"


def test_fresh_ingest_all_groups_unclaimed(store):
    """Regression: a fresh store with no human edits leaves every group
    human_claimed=False (behavior identical to before this fix wave)."""
    ingest(store)
    cache = Cache(store.cache_db)
    rows = cache.conn.execute("SELECT human_claimed FROM groups").fetchall()
    cache.close()
    assert rows  # sanity: groups were actually created
    assert all(r["human_claimed"] == 0 for r in rows)


@pytest.fixture
def two_pose_store(tmp_path) -> Config:
    """A single folder with two poses of the same model — group_folder puts
    both under one ModelGroup (shared 'goblin' core), so a single note is
    written with two files entries."""
    root = tmp_path / "store"
    kit = root / "GoblinCo" / "2024-03"
    kit.mkdir(parents=True)
    trimesh.creation.box(extents=[5, 5, 30]).export(kit / "goblin_pose1.stl")
    trimesh.creation.box(extents=[5, 5, 31]).export(kit / "goblin_pose2.stl")
    return Config(
        store_root=root,
        vault_dir=tmp_path / "vault",
        thumbs_dir=tmp_path / "thumbs",
        footprints_dir=tmp_path / "footprints",
        cache_db=tmp_path / "cache.db",
    )


def _the_only_note(vault_dir):
    notes = list((vault_dir / "models").glob("*.md"))
    assert len(notes) == 1
    return notes[0]


def test_human_removal_persists_and_group_becomes_claimed(two_pose_store):
    """FINDING 1 effect (1), part A: removing an entry from a note's files:
    list and re-ingesting must not re-add it, and the group must become
    human_claimed."""
    ingest(two_pose_store)
    note_path = _the_only_note(two_pose_store.vault_dir)
    post = frontmatter.load(note_path)
    assert len(post.metadata["files"]) == 2
    removed_hash = post.metadata["files"][1]["hash"]
    post.metadata["files"] = post.metadata["files"][:1]
    with open(note_path, "w", encoding="utf-8") as f:
        frontmatter.dump(post, f)

    ingest(two_pose_store)

    reloaded = frontmatter.load(note_path)
    remaining_hashes = {f["hash"] for f in reloaded.metadata["files"]}
    assert removed_hash not in remaining_hashes

    cache = Cache(two_pose_store.cache_db)
    row = cache.conn.execute(
        "SELECT human_claimed FROM groups WHERE group_id=?", (reloaded.metadata["id"],)
    ).fetchone()
    cache.close()
    assert row["human_claimed"] == 1


def test_third_ingest_leaves_claimed_note_untouched(two_pose_store):
    """FINDING 1 effect (1), part B: after the removal is claimed, a further
    ingest must leave the note byte-for-byte untouched (it is no longer even
    reconsidered for regrouping — its remaining member is excluded from the
    folder scan via claimed_hashes)."""
    ingest(two_pose_store)
    note_path = _the_only_note(two_pose_store.vault_dir)
    post = frontmatter.load(note_path)
    post.metadata["files"] = post.metadata["files"][:1]
    with open(note_path, "w", encoding="utf-8") as f:
        frontmatter.dump(post, f)
    ingest(two_pose_store)

    models_dir = two_pose_store.vault_dir / "models"
    before_bytes = note_path.read_bytes()
    before_names = {p.name for p in models_dir.glob("*.md")}
    ingest(two_pose_store)

    assert note_path.read_bytes() == before_bytes
    # The models directory's file-set is what actually catches a fragment
    # note appearing — byte-equality of the original note alone would miss a
    # stray singleton note for the removed member showing up alongside it.
    assert {p.name for p in models_dir.glob("*.md")} == before_names


def test_hash_moved_by_hand_to_another_note_stays_and_old_group_drops_it(two_pose_store):
    """FINDING 1 effect (2): a hash the human manually relocates into a
    different note's files: list stays there (existing human-added-member
    behavior), while its original group drops it via prior_hashes."""
    ingest(two_pose_store)
    goblin_note = _the_only_note(two_pose_store.vault_dir)
    post = frontmatter.load(goblin_note)
    moved_entry = dict(post.metadata["files"][1])
    moved_hash = moved_entry["hash"]

    # Human removes it from its original note...
    post.metadata["files"] = post.metadata["files"][:1]
    with open(goblin_note, "w", encoding="utf-8") as f:
        frontmatter.dump(post, f)

    # ...and manually declares it part of a different, unrelated model.
    other_note = two_pose_store.vault_dir / "models" / "manual-other.md"
    other_post = frontmatter.Post(
        "# Other Model\n",
        id="manual0",
        type="model",
        title="Other Model",
        files=[moved_entry],
    )
    with open(other_note, "w", encoding="utf-8") as f:
        frontmatter.dump(other_post, f)

    ingest(two_pose_store)

    other_after = frontmatter.load(other_note)
    assert {f["hash"] for f in other_after.metadata["files"]} == {moved_hash}

    goblin_after = frontmatter.load(goblin_note)
    assert moved_hash not in {f["hash"] for f in goblin_after.metadata["files"]}


def test_relocated_hash_never_resurfaces_as_fragment(two_pose_store):
    """FINDING B, test (a): a hash relocated by hand into a different note
    must never resurface as its own fragment note, on this ingest or any
    later one — the removal tombstone permanently excludes it from
    regrouping. A third ingest (no further edits) is then a full no-op."""
    ingest(two_pose_store)
    goblin_note = _the_only_note(two_pose_store.vault_dir)
    post = frontmatter.load(goblin_note)
    moved_entry = dict(post.metadata["files"][1])

    post.metadata["files"] = post.metadata["files"][:1]
    with open(goblin_note, "w", encoding="utf-8") as f:
        frontmatter.dump(post, f)

    other_note = two_pose_store.vault_dir / "models" / "manual-other.md"
    other_post = frontmatter.Post(
        "# Other Model\n",
        id="manual0",
        type="model",
        title="Other Model",
        files=[moved_entry],
    )
    with open(other_note, "w", encoding="utf-8") as f:
        frontmatter.dump(other_post, f)

    models_dir = two_pose_store.vault_dir / "models"
    before_names = {p.name for p in models_dir.glob("*.md")}

    ingest(two_pose_store)  # divergence discovered; removal tombstone created
    assert {p.name for p in models_dir.glob("*.md")} == before_names

    ingest(two_pose_store)  # a fragment for the relocated hash would appear here
    assert {p.name for p in models_dir.glob("*.md")} == before_names

    s3 = ingest(two_pose_store)
    assert (s3.created, s3.updated) == (0, 0)
    assert {p.name for p in models_dir.glob("*.md")} == before_names


def test_removed_hash_no_fragment_across_two_ingests(two_pose_store):
    """FINDING B, test (b) part 1: a pure removal (no relocation elsewhere)
    must not resurface as a fragment note across two consecutive ingests."""
    ingest(two_pose_store)
    note_path = _the_only_note(two_pose_store.vault_dir)
    post = frontmatter.load(note_path)
    post.metadata["files"] = post.metadata["files"][:1]
    with open(note_path, "w", encoding="utf-8") as f:
        frontmatter.dump(post, f)

    models_dir = two_pose_store.vault_dir / "models"
    before_names = {p.name for p in models_dir.glob("*.md")}

    ingest(two_pose_store)
    assert {p.name for p in models_dir.glob("*.md")} == before_names
    ingest(two_pose_store)
    assert {p.name for p in models_dir.glob("*.md")} == before_names


def test_removed_hash_tombstone_survives_cache_rebuild(two_pose_store):
    """FINDING B, test (b) part 2 — the founding constraint: "no state lives
    only in SQLite". After cache loss + rebuild, the removal tombstone must
    be RE-DERIVED from disk + vault alone, so the removed hash still doesn't
    resurface as a fragment note post-rebuild."""
    ingest(two_pose_store)
    note_path = _the_only_note(two_pose_store.vault_dir)
    post = frontmatter.load(note_path)
    post.metadata["files"] = post.metadata["files"][:1]
    with open(note_path, "w", encoding="utf-8") as f:
        frontmatter.dump(post, f)

    models_dir = two_pose_store.vault_dir / "models"
    before_names = {p.name for p in models_dir.glob("*.md")}

    ingest(two_pose_store)
    ingest(two_pose_store)
    assert {p.name for p in models_dir.glob("*.md")} == before_names

    two_pose_store.cache_db.unlink()
    rebuild_cache(two_pose_store)

    ingest(two_pose_store)
    assert {p.name for p in models_dir.glob("*.md")} == before_names


def test_cross_folder_duplicate_content_does_not_hijack_note(tmp_path):
    """FINDING A regression: two campaign folders under one creator share
    one content-identical file plus distinct partners. A raw hash-overlap
    note match (no folder check) would hijack the first folder's note,
    collapsing all three files into one note and mis-claiming the mangled
    union. The folder-scoped overlap rule must fall back to the
    disambiguated-fork path instead (the pre-fix collision behavior, which
    is correct for genuinely unrelated groups). This test fails without the
    folder check.
    """
    root = tmp_path / "store"
    (root / "Creator" / "2024-03").mkdir(parents=True)
    (root / "Creator" / "2024-04").mkdir(parents=True)
    trimesh.creation.box(extents=[5, 5, 30]).export(
        root / "Creator" / "2024-03" / "goblin_pose1.stl"
    )
    trimesh.creation.box(extents=[5, 5, 31]).export(
        root / "Creator" / "2024-03" / "goblin_pose2.stl"
    )
    # Content-identical duplicate of 2024-03's pose1, dropped into a
    # different campaign folder alongside a distinct partner file.
    (root / "Creator" / "2024-04" / "goblin_pose1.stl").write_bytes(
        (root / "Creator" / "2024-03" / "goblin_pose1.stl").read_bytes()
    )
    trimesh.creation.box(extents=[5, 5, 32]).export(
        root / "Creator" / "2024-04" / "goblin_pose3.stl"
    )
    cfg = Config(
        store_root=root,
        vault_dir=tmp_path / "vault",
        thumbs_dir=tmp_path / "thumbs",
        footprints_dir=tmp_path / "footprints",
        cache_db=tmp_path / "cache.db",
    )

    ingest(cfg)

    notes = list((cfg.vault_dir / "models").glob("*.md"))
    assert len(notes) == 2

    original_note = cfg.vault_dir / "models" / "creator--goblin.md"
    assert original_note.exists()
    original_meta = frontmatter.load(original_note).metadata
    assert {f["path"] for f in original_meta["files"]} == {
        "Creator/2024-03/goblin_pose1.stl",
        "Creator/2024-03/goblin_pose2.stl",
    }

    cache = Cache(cfg.cache_db)
    rows = cache.conn.execute("SELECT human_claimed FROM groups").fetchall()
    cache.close()
    assert rows
    assert all(r["human_claimed"] == 0 for r in rows)

    s2 = ingest(cfg)
    assert (s2.created, s2.updated) == (0, 0)
    assert s2.unchanged == 2
