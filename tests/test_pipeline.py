import zipfile

import pytest
import trimesh

from stl_curator.config import Config
from stl_curator.pipeline import ingest


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
    import frontmatter

    ingest(store)
    note = next((store.vault_dir / "models").glob("*troll*.md"))
    post = frontmatter.load(note)
    post["status"] = "painted"
    with open(note, "w", encoding="utf-8") as f:
        frontmatter.dump(post, f)
    ingest(store)
    assert frontmatter.load(note)["status"] == "painted"
