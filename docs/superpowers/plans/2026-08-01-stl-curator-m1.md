# STL Curator Milestone 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the local-only ingest spine: scan → hash → group → mesh facts → thumbnails → Obsidian vault generation → duplicate report, per spec `docs/superpowers/specs/2026-08-01-stl-curator-m1-design.md`.

**Architecture:** A `typer` CLI drives idempotent pipeline stages over an STL store. Content hashes are identity everywhere. Grouping is folder-first with vocab-driven stem clustering (rapidfuzz). Vault notes are merge-aware markdown+frontmatter; SQLite is a rebuildable cache only.

**Tech Stack:** Python 3.11+, uv, ruff, pytest, typer, trimesh, pyrender (fallback: trimesh save_image), Pillow, rapidfuzz, python-frontmatter, tomllib/tomli-w, sqlite3 (stdlib).

## Global Constraints

- Python `>=3.11`; all commands via `uv run …`; ruff is the only linter/formatter.
- **Never modify, rename, or delete files in the STL store.** Extraction creates new directories only; originals never deleted (spec §5.2).
- Vault (`vault/`) is self-contained: vault-internal wikilinks and vault-root-relative references only; code reads its location from config only (spec §2).
- No state lives only in SQLite — everything rebuildable from disk + frontmatter (spec §6).
- Errors never halt ingest; they are recorded and reported (spec §6).
- File hash = SHA-256 hex (lowercase). Group id = first 8 hex chars of SHA-256 over sorted member hashes joined with `\n` (spec §3, §4.1).
- Tests: parametrized, atomic named cases (`pytest.mark.parametrize`) — never loops inside a test body (user global preference).
- All frontmatter paths: POSIX separators, relative to `store_root` (spec §3).
- Windows long paths: wrap absolute paths with `\\?\` prefix helper for file I/O (spec §6).
- Commit after every task with a conventional-commit message; append the standard co-author trailer used in this repo.

---

### Task 1: Project scaffold and config loader

**Files:**
- Create: `pyproject.toml`, `config.example.toml`, `src/stl_curator/__init__.py`, `src/stl_curator/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Config` dataclass with fields `store_root: Path`, `vault_dir: Path`, `thumbs_dir: Path`, `footprints_dir: Path`, `cache_db: Path`, `group_max_simple: int = 6`, `group_similarity: int = 80`, `group_confidence_min: float = 0.6`; `load_config(path: Path | None = None, **overrides) -> Config` (overrides win over file values; file values win over defaults). `long_path(p: Path) -> str` helper in `config.py`.

- [ ] **Step 1: Scaffold project**

```bash
cd C:/dev/STL_curator
uv init --lib --name stl-curator --python 3.11 .   # keep existing files; if uv balks, create pyproject manually per below
uv add typer trimesh pyrender numpy pillow rapidfuzz python-frontmatter tomli-w
uv add --dev pytest ruff
```

`pyproject.toml` must end up containing (merge into what `uv init` makes):

```toml
[project]
name = "stl-curator"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "typer", "trimesh", "pyrender", "numpy", "pillow",
    "rapidfuzz", "python-frontmatter", "tomli-w",
]

[project.scripts]
stl-curator = "stl_curator.cli:app"

[dependency-groups]
dev = ["pytest", "ruff"]

[tool.ruff]
line-length = 100
src = ["src", "tests"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/stl_curator"]
```

`config.example.toml`:

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

- [ ] **Step 2: Write the failing tests**

`tests/test_config.py`:

```python
from pathlib import Path
import pytest
from stl_curator.config import Config, load_config, long_path


def test_defaults_when_no_file(tmp_path):
    cfg = load_config(None, store_root=tmp_path, vault_dir=tmp_path / "v",
                      thumbs_dir=tmp_path / "t", footprints_dir=tmp_path / "f",
                      cache_db=tmp_path / "c.db")
    assert cfg.group_max_simple == 6
    assert cfg.group_similarity == 80
    assert cfg.group_confidence_min == 0.6


def test_file_values_loaded(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('store_root = "X:/store"\nvault_dir = "X:/vault"\n'
                 'thumbs_dir = "X:/thumbs"\nfootprints_dir = "X:/fp"\n'
                 'cache_db = "X:/cache.db"\ngroup_max_simple = 9\n')
    cfg = load_config(p)
    assert cfg.store_root == Path("X:/store")
    assert cfg.group_max_simple == 9


def test_overrides_beat_file(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('store_root = "X:/store"\nvault_dir = "X:/vault"\n'
                 'thumbs_dir = "X:/thumbs"\nfootprints_dir = "X:/fp"\n'
                 'cache_db = "X:/cache.db"\n')
    cfg = load_config(p, store_root=Path("Y:/other"))
    assert cfg.store_root == Path("Y:/other")


@pytest.mark.parametrize("given,expected", [
    (Path("C:/x/y.stl"), "\\\\?\\C:\\x\\y.stl"),
    (Path("relative/y.stl"), str(Path("relative/y.stl"))),  # relative paths unwrapped
])
def test_long_path(given, expected):
    assert long_path(given) == expected
```

- [ ] **Step 3: Run to verify failure** — `uv run pytest tests/test_config.py -v` → import errors.

- [ ] **Step 4: Implement `src/stl_curator/config.py`**

```python
from __future__ import annotations
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

_PATH_FIELDS = {"store_root", "vault_dir", "thumbs_dir", "footprints_dir", "cache_db"}


@dataclass
class Config:
    store_root: Path
    vault_dir: Path
    thumbs_dir: Path
    footprints_dir: Path
    cache_db: Path
    group_max_simple: int = 6
    group_similarity: int = 80
    group_confidence_min: float = 0.6


def load_config(path: Path | None = None, **overrides) -> Config:
    data: dict = {}
    if path is not None and Path(path).exists():
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    data.update({k: v for k, v in overrides.items() if v is not None})
    kwargs = {}
    for f in fields(Config):
        if f.name in data:
            v = data[f.name]
            kwargs[f.name] = Path(v) if f.name in _PATH_FIELDS else v
    return Config(**kwargs)


def long_path(p: Path) -> str:
    """Windows long-path-safe string for file I/O. Absolute paths get \\\\?\\."""
    if p.is_absolute():
        return "\\\\?\\" + str(p)
    return str(p)
```

- [ ] **Step 5: Run tests to verify pass** — `uv run pytest tests/test_config.py -v`; also `uv run ruff check` and `uv run ruff format`.

- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat: project scaffold with uv, config loader"`

---

### Task 2: Hashing and store scan

**Files:**
- Create: `src/stl_curator/scan.py`
- Test: `tests/test_scan.py`

**Interfaces:**
- Consumes: `long_path` from Task 1.
- Produces: `FileRecord` dataclass: `rel_path: str` (POSIX, relative to root), `abs_path: Path`, `hash: str`, `size: int`, `mtime: float`, `kind: str` (`"stl" | "zip" | "image" | "other"`); `hash_file(path: Path) -> str`; `scan_store(root: Path) -> list[FileRecord]` (sorted by `rel_path`; skips directories named `_extracted` is NOT needed — extraction dirs are normal content; skips hidden files starting with `.`).
- `IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}` exported.

- [ ] **Step 1: Write the failing tests**

`tests/test_scan.py`:

```python
import hashlib
from pathlib import Path
import pytest
from stl_curator.scan import FileRecord, hash_file, scan_store


@pytest.fixture
def store(tmp_path):
    (tmp_path / "GoblinCo" / "2024-03").mkdir(parents=True)
    (tmp_path / "GoblinCo" / "2024-03" / "goblin.stl").write_bytes(b"solid a\nendsolid\n")
    (tmp_path / "GoblinCo" / "2024-03" / "render.png").write_bytes(b"\x89PNG fake")
    (tmp_path / "GoblinCo" / "kit.zip").write_bytes(b"PK fake")
    (tmp_path / "GoblinCo" / ".hidden").write_bytes(b"x")
    (tmp_path / "readme.txt").write_bytes(b"hi")
    return tmp_path


def test_hash_file_is_sha256(tmp_path):
    p = tmp_path / "a.stl"
    p.write_bytes(b"hello")
    assert hash_file(p) == hashlib.sha256(b"hello").hexdigest()


def test_scan_finds_all_visible_files(store):
    recs = scan_store(store)
    assert [r.rel_path for r in recs] == [
        "GoblinCo/2024-03/goblin.stl",
        "GoblinCo/2024-03/render.png",
        "GoblinCo/kit.zip",
        "readme.txt",
    ]


@pytest.mark.parametrize("rel,kind", [
    ("GoblinCo/2024-03/goblin.stl", "stl"),
    ("GoblinCo/2024-03/render.png", "image"),
    ("GoblinCo/kit.zip", "zip"),
    ("readme.txt", "other"),
])
def test_kind_classification(store, rel, kind):
    recs = {r.rel_path: r for r in scan_store(store)}
    assert recs[rel].kind == kind


def test_hidden_files_skipped(store):
    assert not any(".hidden" in r.rel_path for r in scan_store(store))
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_scan.py -v`

- [ ] **Step 3: Implement `src/stl_curator/scan.py`**

```python
from __future__ import annotations
import hashlib
from dataclasses import dataclass
from pathlib import Path

from stl_curator.config import long_path

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
_KIND_BY_EXT = {".stl": "stl", ".zip": "zip", **{e: "image" for e in IMAGE_EXTS}}


@dataclass
class FileRecord:
    rel_path: str
    abs_path: Path
    hash: str
    size: int
    mtime: float
    kind: str


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(long_path(path), "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_store(root: Path) -> list[FileRecord]:
    records = []
    for p in root.rglob("*"):
        if not p.is_file() or p.name.startswith("."):
            continue
        stat = p.stat()
        records.append(FileRecord(
            rel_path=p.relative_to(root).as_posix(),
            abs_path=p,
            hash=hash_file(p),
            size=stat.st_size,
            mtime=stat.st_mtime,
            kind=_KIND_BY_EXT.get(p.suffix.lower(), "other"),
        ))
    records.sort(key=lambda r: r.rel_path)
    return records
```

- [ ] **Step 4: Run tests to verify pass**, ruff check/format.

- [ ] **Step 5: Commit** — `git commit -m "feat: store scanner with sha256 hashing"`

---

### Task 3: SQLite cache

**Files:**
- Create: `src/stl_curator/cache.py`
- Test: `tests/test_cache.py`

**Interfaces:**
- Consumes: `FileRecord` (Task 2).
- Produces: class `Cache` — `__init__(self, db_path: Path)` (creates schema, `:memory:` allowed for tests); methods:
  - `upsert_file(rec: FileRecord) -> None`
  - `file_unchanged(rec: FileRecord) -> bool` (same rel_path with same hash already stored)
  - `get_files() -> list[sqlite3.Row]` (columns: hash, rel_path, size, mtime, kind)
  - `set_mesh_facts(hash: str, height_mm: float | None, triangles: int | None, watertight: bool | None, error: str | None) -> None`
  - `get_mesh_facts(hash: str) -> sqlite3.Row | None`
  - `upsert_group(group_id: str, member_hashes: list[str], confidence: float, human_claimed: bool = False) -> None`
  - `claimed_hashes() -> set[str]`
  - `set_thumb(hash: str, source: str) -> None`  (`source` in `harvested|rendered|missing`)
  - `duplicate_hashes() -> dict[str, list[str]]` (hash → rel_paths, only where >1 path)
  - `clear() -> None` (drop + recreate all tables; used by rebuild)
  - `close() -> None`

- [ ] **Step 1: Write the failing tests**

`tests/test_cache.py`:

```python
from pathlib import Path
import pytest
from stl_curator.cache import Cache
from stl_curator.scan import FileRecord


def rec(rel="a/b.stl", h="h1", size=3, mtime=1.0, kind="stl"):
    return FileRecord(rel, Path("/x") / rel, h, size, mtime, kind)


@pytest.fixture
def cache():
    return Cache(Path(":memory:"))


def test_upsert_and_unchanged(cache):
    cache.upsert_file(rec())
    assert cache.file_unchanged(rec()) is True
    assert cache.file_unchanged(rec(h="h2")) is False
    assert cache.file_unchanged(rec(rel="other.stl")) is False


def test_upsert_same_path_updates(cache):
    cache.upsert_file(rec(h="h1"))
    cache.upsert_file(rec(h="h2"))
    rows = cache.get_files()
    assert len(rows) == 1 and rows[0]["hash"] == "h2"


def test_mesh_facts_roundtrip(cache):
    cache.upsert_file(rec())
    cache.set_mesh_facts("h1", 48.2, 1000, True, None)
    row = cache.get_mesh_facts("h1")
    assert row["height_mm"] == 48.2 and row["watertight"] == 1


def test_group_claimed(cache):
    cache.upsert_group("g1", ["h1", "h2"], 0.9, human_claimed=True)
    cache.upsert_group("g2", ["h3"], 0.5)
    assert cache.claimed_hashes() == {"h1", "h2"}


def test_duplicates(cache):
    cache.upsert_file(rec(rel="a.stl", h="same"))
    cache.upsert_file(rec(rel="b.stl", h="same"))
    cache.upsert_file(rec(rel="c.stl", h="uniq"))
    assert cache.duplicate_hashes() == {"same": ["a.stl", "b.stl"]}


def test_clear(cache):
    cache.upsert_file(rec())
    cache.clear()
    assert cache.get_files() == []
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement `src/stl_curator/cache.py`**

```python
from __future__ import annotations
import json
import sqlite3
from pathlib import Path

from stl_curator.scan import FileRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files(
  rel_path TEXT PRIMARY KEY, hash TEXT NOT NULL,
  size INTEGER, mtime REAL, kind TEXT);
CREATE INDEX IF NOT EXISTS idx_files_hash ON files(hash);
CREATE TABLE IF NOT EXISTS mesh_facts(
  hash TEXT PRIMARY KEY, height_mm REAL, triangles INTEGER,
  watertight INTEGER, error TEXT);
CREATE TABLE IF NOT EXISTS groups(
  group_id TEXT PRIMARY KEY, member_hashes TEXT NOT NULL,
  confidence REAL, human_claimed INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS thumbs(hash TEXT PRIMARY KEY, source TEXT);
"""


class Cache:
    def __init__(self, db_path: Path):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)

    def upsert_file(self, rec: FileRecord) -> None:
        self.conn.execute(
            "INSERT INTO files(rel_path,hash,size,mtime,kind) VALUES(?,?,?,?,?) "
            "ON CONFLICT(rel_path) DO UPDATE SET hash=excluded.hash, "
            "size=excluded.size, mtime=excluded.mtime, kind=excluded.kind",
            (rec.rel_path, rec.hash, rec.size, rec.mtime, rec.kind))
        self.conn.commit()

    def file_unchanged(self, rec: FileRecord) -> bool:
        row = self.conn.execute(
            "SELECT hash FROM files WHERE rel_path=?", (rec.rel_path,)).fetchone()
        return bool(row) and row["hash"] == rec.hash

    def get_files(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM files ORDER BY rel_path").fetchall()

    def set_mesh_facts(self, hash: str, height_mm, triangles, watertight, error) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO mesh_facts VALUES(?,?,?,?,?)",
            (hash, height_mm, triangles,
             None if watertight is None else int(watertight), error))
        self.conn.commit()

    def get_mesh_facts(self, hash: str):
        return self.conn.execute(
            "SELECT * FROM mesh_facts WHERE hash=?", (hash,)).fetchone()

    def upsert_group(self, group_id: str, member_hashes: list[str],
                     confidence: float, human_claimed: bool = False) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO groups VALUES(?,?,?,?)",
            (group_id, json.dumps(sorted(member_hashes)), confidence,
             int(human_claimed)))
        self.conn.commit()

    def claimed_hashes(self) -> set[str]:
        out: set[str] = set()
        for row in self.conn.execute(
                "SELECT member_hashes FROM groups WHERE human_claimed=1"):
            out.update(json.loads(row["member_hashes"]))
        return out

    def set_thumb(self, hash: str, source: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO thumbs VALUES(?,?)", (hash, source))
        self.conn.commit()

    def duplicate_hashes(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        rows = self.conn.execute(
            "SELECT hash, rel_path FROM files WHERE hash IN "
            "(SELECT hash FROM files GROUP BY hash HAVING COUNT(*)>1) "
            "ORDER BY hash, rel_path").fetchall()
        for r in rows:
            out.setdefault(r["hash"], []).append(r["rel_path"])
        return out

    def clear(self) -> None:
        for t in ("files", "mesh_facts", "groups", "thumbs"):
            self.conn.execute(f"DROP TABLE IF EXISTS {t}")
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
```

- [ ] **Step 4: Run tests, ruff.**
- [ ] **Step 5: Commit** — `git commit -m "feat: rebuildable sqlite cache"`

---

### Task 4: Zip inventory and extraction

**Files:**
- Create: `src/stl_curator/zips.py`
- Test: `tests/test_zips.py`

**Interfaces:**
- Consumes: `FileRecord` (Task 2), `long_path` (Task 1).
- Produces: `extract_needed_zips(records: list[FileRecord], root: Path) -> list[Path]` — for each `kind=="zip"` record: target dir = zip path without `.zip` suffix; if target dir already exists (creator shipped both, or previously extracted) → skip; else extract there. Returns list of directories extracted this run. Zip errors (`BadZipFile`) are caught; the zip is skipped and returned via second mechanism: function returns `ExtractResult` dataclass `(extracted: list[Path], errors: list[tuple[str, str]])` (rel_path, message). Originals never deleted.

- [ ] **Step 1: Write the failing tests**

`tests/test_zips.py`:

```python
import zipfile
from pathlib import Path
import pytest
from stl_curator.scan import scan_store
from stl_curator.zips import ExtractResult, extract_needed_zips


def make_zip(path: Path, names: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        for n in names:
            z.writestr(n, b"solid\nendsolid\n")


def test_extracts_new_zip(tmp_path):
    make_zip(tmp_path / "C" / "kit.zip", ["a.stl", "sub/b.stl"])
    res = extract_needed_zips(scan_store(tmp_path), tmp_path)
    assert res.extracted == [tmp_path / "C" / "kit"]
    assert (tmp_path / "C" / "kit" / "sub" / "b.stl").exists()
    assert (tmp_path / "C" / "kit.zip").exists()  # original untouched


def test_skips_when_dir_exists(tmp_path):
    make_zip(tmp_path / "C" / "kit.zip", ["a.stl"])
    (tmp_path / "C" / "kit").mkdir(parents=True)
    res = extract_needed_zips(scan_store(tmp_path), tmp_path)
    assert res.extracted == []


def test_bad_zip_reported_not_raised(tmp_path):
    bad = tmp_path / "C" / "bad.zip"
    bad.parent.mkdir(parents=True)
    bad.write_bytes(b"this is not a zip")
    res = extract_needed_zips(scan_store(tmp_path), tmp_path)
    assert res.extracted == []
    assert res.errors and res.errors[0][0] == "C/bad.zip"
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement `src/stl_curator/zips.py`**

```python
from __future__ import annotations
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from stl_curator.scan import FileRecord


@dataclass
class ExtractResult:
    extracted: list[Path] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)


def extract_needed_zips(records: list[FileRecord], root: Path) -> ExtractResult:
    res = ExtractResult()
    for rec in records:
        if rec.kind != "zip":
            continue
        target = rec.abs_path.with_suffix("")
        if target.exists():
            continue
        try:
            with zipfile.ZipFile(rec.abs_path) as z:
                z.extractall(target)
            res.extracted.append(target)
        except (zipfile.BadZipFile, OSError) as e:
            res.errors.append((rec.rel_path, str(e)))
    return res
```

- [ ] **Step 4: Run tests, ruff.**
- [ ] **Step 5: Commit** — `git commit -m "feat: zip inventory and extract-if-needed"`

---

### Task 5: Grouping vocabulary and name normalization

**Files:**
- Create: `src/stl_curator/grouping_vocab.toml`, `src/stl_curator/grouping.py` (normalization half)
- Test: `tests/test_normalize.py`

**Interfaces:**
- Produces: `Vocab` dataclass (`variant_words: set[str]`, `part_words: set[str]`, `marker_words: set[str]`, loaded via `load_vocab(path: Path | None = None) -> Vocab`; `None` loads the packaged default via `importlib.resources`); `NormalizedName` dataclass: `core: str`, `role: str` (`"variant" | "part" | "model"`), `markers: set[str]`; `normalize_stem(filename: str, vocab: Vocab) -> NormalizedName`.
- Normalization algorithm: take stem (no extension), lowercase, replace `[-. ]` with `_`, split on `_`, drop empty tokens; classify each token from the END of the list: pure digits or single letters `a`–`d` or `posN`/`poseN` or in `variant_words` → variant evidence (drop token); in `part_words` (also matches `partNN`, `wing_l` style via base word) → part evidence (drop); in `marker_words` or scale patterns (`\d+mm`, `x\d+(\.\d+)?`) → marker (drop); stop at first unclassified token. Remaining tokens joined with `_` = `core`. Role: `part` if any part evidence, else `variant` if any variant evidence, else `model`.

- [ ] **Step 1: Create `src/stl_curator/grouping_vocab.toml`**

```toml
# Data, not code: tune against example_stls without touching logic (spec §5.3).
variant_words = [
  "pose", "alt", "variant", "sword", "spear", "axe", "bow", "shield",
  "helmet", "helm", "hooded", "cape", "cloak", "left", "right",
]
part_words = [
  "body", "head", "torso", "arm", "arms", "leg", "legs", "wing", "wings",
  "tail", "base", "part", "half", "top", "bottom", "upper", "lower",
]
marker_words = [
  "supported", "unsupported", "presupported", "presup", "sup", "hollow",
  "solid", "lys", "fixed", "repaired", "final",
]
```

Note: `left`/`right` appear in variant_words (weapon-in-left-hand style) but bare `l`/`r`/`01` after a part word bind to the part (`wing_l`). The token classifier handles this by consuming trailing single letters/digits *before* the word they follow.

- [ ] **Step 2: Write the failing tests**

`tests/test_normalize.py`:

```python
import pytest
from stl_curator.grouping import load_vocab, normalize_stem

VOCAB = load_vocab()


@pytest.mark.parametrize("filename,core,role", [
    ("goblin_pose1.stl", "goblin", "variant"),
    ("goblin_pose2.stl", "goblin", "variant"),
    ("goblin_helmet.stl", "goblin", "variant"),
    ("goblin_spear_a.stl", "goblin", "variant"),
    ("Goblin Archer.stl", "goblin_archer", "model"),
    ("dragon_body.stl", "dragon", "part"),
    ("dragon_wing_l.stl", "dragon", "part"),
    ("dragon_tail_01.stl", "dragon", "part"),
    ("owlbear_part03.stl", "owlbear", "part"),
    ("troll_32mm_supported.stl", "troll", "model"),
    ("troll-big.final.stl", "troll_big", "model"),
])
def test_normalize_core_and_role(filename, core, role):
    n = normalize_stem(filename, VOCAB)
    assert (n.core, n.role) == (core, role)


@pytest.mark.parametrize("filename,markers", [
    ("troll_32mm_supported.stl", {"32mm", "supported"}),
    ("goblin_presup.stl", {"presup"}),
    ("goblin.stl", set()),
])
def test_markers_captured(filename, markers):
    assert normalize_stem(filename, VOCAB).markers == markers
```

- [ ] **Step 3: Run to verify failure.**

- [ ] **Step 4: Implement normalization half of `src/stl_curator/grouping.py`**

```python
from __future__ import annotations
import re
import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

_SCALE_RE = re.compile(r"^(\d+mm|x\d+(\.\d+)?)$")
_POSE_RE = re.compile(r"^poses?\d*$|^pos\d+$")
_PART_N_RE = re.compile(r"^part\d+$")
_TRAIL_RE = re.compile(r"^(\d+|[a-d]|l|r)$")


@dataclass
class Vocab:
    variant_words: set[str]
    part_words: set[str]
    marker_words: set[str]


@dataclass
class NormalizedName:
    core: str
    role: str
    markers: set[str] = field(default_factory=set)


def load_vocab(path: Path | None = None) -> Vocab:
    if path is None:
        raw = resources.files("stl_curator").joinpath("grouping_vocab.toml").read_text()
    else:
        raw = Path(path).read_text(encoding="utf-8")
    d = tomllib.loads(raw)
    return Vocab(set(d["variant_words"]), set(d["part_words"]), set(d["marker_words"]))


def normalize_stem(filename: str, vocab: Vocab) -> NormalizedName:
    stem = Path(filename).stem.lower()
    tokens = [t for t in re.split(r"[-. _]+", stem) if t]
    markers: set[str] = set()
    saw_variant = saw_part = False
    while tokens:
        tok = tokens[-1]
        if _TRAIL_RE.match(tok) and len(tokens) > 1:
            nxt = tokens[-2]
            if nxt in vocab.part_words:          # wing_l, tail_01 → bind to part
                tokens.pop(); continue
            if _POSE_RE.match(nxt) or nxt in vocab.variant_words:
                tokens.pop(); continue
            if _TRAIL_RE.match(tok) and tok.isdigit() is False and tok in ("a", "b", "c", "d"):
                saw_variant = True; tokens.pop(); continue
            if tok.isdigit():                     # bare trailing number: pose-ish
                saw_variant = True; tokens.pop(); continue
            tokens.pop(); continue
        if _POSE_RE.match(tok):
            saw_variant = True; tokens.pop(); continue
        if _PART_N_RE.match(tok):
            saw_part = True; tokens.pop(); continue
        if tok in vocab.part_words:
            saw_part = True; tokens.pop(); continue
        if tok in vocab.variant_words:
            saw_variant = True; tokens.pop(); continue
        if tok in vocab.marker_words or _SCALE_RE.match(tok):
            markers.add(tok); tokens.pop(); continue
        break
    core = "_".join(tokens) if tokens else stem.replace(" ", "_")
    role = "part" if saw_part else ("variant" if saw_variant else "model")
    return NormalizedName(core=core, role=role, markers=markers)
```

- [ ] **Step 5: Run tests to verify pass.** Iterate on the classifier until the parametrized table passes — the table is the contract; if a case is genuinely ambiguous, adjust the *vocab file*, not the test.

- [ ] **Step 6: Commit** — `git commit -m "feat: grouping vocab and filename normalization"`

---

### Task 6: Stem clustering, assembly, confidence, group identity

**Files:**
- Modify: `src/stl_curator/grouping.py` (add clustering half)
- Test: `tests/test_grouping.py`

**Interfaces:**
- Consumes: `NormalizedName`, `Vocab`, `normalize_stem` (Task 5); `FileRecord` (Task 2); `Config` (Task 1); rapidfuzz.
- Produces:
  - `GroupMember` dataclass: `record: FileRecord`, `role: str`.
  - `ModelGroup` dataclass: `members: list[GroupMember]`, `title: str` (core with `_`→space, title-cased), `assembly: str`, `confidence: float`; property `id: str` → `group_id([m.record.hash for m in members])`.
  - `group_id(hashes: list[str]) -> str` — sha256 over `"\n".join(sorted(hashes))`, first 8 hex.
  - `group_folder(stl_records: list[FileRecord], vocab: Vocab, cfg: Config) -> list[ModelGroup]` — records are the STLs of ONE leaf folder. Algorithm: normalize all stems; bucket by exact `core`; then merge buckets whose cores score `>= cfg.group_similarity` with `rapidfuzz.fuzz.token_set_ratio`. Confidence per group = mean pairwise core similarity /100 (1.0 for singletons and exact-core groups). If folder has `<= cfg.group_max_simple` files AND all cores merge to one group → single group, confidence 1.0. If overall clustering yields any group with confidence `< cfg.group_confidence_min` → return ONE coarse group of the whole folder with `assembly="needs-review"`, confidence = min observed (spec §5.3: never guess fine).
  - Assembly per group from member roles: all `part` (plus ≤1 `model`) → `multipart`; all `variant` → `variants`; single member → `single`; both parts and variants → `mixed`.

- [ ] **Step 1: Write the failing tests**

`tests/test_grouping.py`:

```python
from pathlib import Path
import pytest
from stl_curator.config import Config
from stl_curator.grouping import group_folder, group_id, load_vocab
from stl_curator.scan import FileRecord

VOCAB = load_vocab()
CFG = Config(store_root=Path("."), vault_dir=Path("."), thumbs_dir=Path("."),
             footprints_dir=Path("."), cache_db=Path(":memory:"))


def recs(*names):
    return [FileRecord(f"C/R/{n}", Path(n), f"hash_{n}", 1, 1.0, "stl")
            for n in names]


def by_title(groups):
    return {g.title: sorted(m.record.rel_path.rsplit("/", 1)[-1] for m in g.members)
            for g in groups}


def test_goblin_poses_one_group_variants():
    groups = group_folder(recs("goblin_pose1.stl", "goblin_pose2.stl",
                               "goblin_helmet.stl"), VOCAB, CFG)
    assert len(groups) == 1
    assert groups[0].assembly == "variants"
    assert groups[0].title == "Goblin"


def test_split_dragon_one_group_multipart():
    groups = group_folder(recs("dragon_body.stl", "dragon_wing_l.stl",
                               "dragon_wing_r.stl", "dragon_tail_01.stl"), VOCAB, CFG)
    assert len(groups) == 1
    assert groups[0].assembly == "multipart"


def test_two_distinct_models_two_groups():
    groups = group_folder(recs("goblin_pose1.stl", "goblin_pose2.stl",
                               "troll_king.stl"), VOCAB, CFG)
    assert by_title(groups) == {
        "Goblin": ["goblin_pose1.stl", "goblin_pose2.stl"],
        "Troll King": ["troll_king.stl"],
    }
    assert {g.title: g.assembly for g in groups} == {
        "Goblin": "variants", "Troll King": "single"}


def test_mixed_kit():
    groups = group_folder(recs("giant_body.stl", "giant_head.stl",
                               "giant_axe.stl"), VOCAB, CFG)
    assert len(groups) == 1
    assert groups[0].assembly == "mixed"


@pytest.mark.parametrize("hashes_a,hashes_b,equal", [
    (["h1", "h2"], ["h2", "h1"], True),       # order-invariant
    (["h1", "h2"], ["h1", "h2", "h3"], False),  # membership change
])
def test_group_id_stability(hashes_a, hashes_b, equal):
    assert (group_id(hashes_a) == group_id(hashes_b)) is equal


def test_group_id_is_8_hex():
    gid = group_id(["h1"])
    assert len(gid) == 8 and int(gid, 16) >= 0
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement clustering half (append to `src/stl_curator/grouping.py`)**

```python
import hashlib
from itertools import combinations
from rapidfuzz import fuzz

from stl_curator.config import Config
from stl_curator.scan import FileRecord


@dataclass
class GroupMember:
    record: FileRecord
    role: str


@dataclass
class ModelGroup:
    members: list[GroupMember]
    title: str
    assembly: str
    confidence: float

    @property
    def id(self) -> str:
        return group_id([m.record.hash for m in self.members])


def group_id(hashes: list[str]) -> str:
    joined = "\n".join(sorted(hashes))
    return hashlib.sha256(joined.encode()).hexdigest()[:8]


def _assembly(members: list[GroupMember]) -> str:
    if len(members) == 1:
        return "single"
    roles = {m.role for m in members}
    if "part" in roles and "variant" in roles:
        return "mixed"
    if "part" in roles:
        return "multipart"
    if "variant" in roles:
        return "variants"
    return "needs-review"  # several files, no evidence they relate


def group_folder(stl_records: list[FileRecord], vocab: Vocab,
                 cfg: Config) -> list[ModelGroup]:
    if not stl_records:
        return []
    normalized = [(r, normalize_stem(Path(r.rel_path).name, vocab))
                  for r in stl_records]
    buckets: dict[str, list[tuple[FileRecord, NormalizedName]]] = {}
    for r, n in normalized:
        buckets.setdefault(n.core, []).append((r, n))

    cores = sorted(buckets)
    merged: list[list[str]] = []
    for core in cores:
        placed = False
        for cluster in merged:
            if any(fuzz.token_set_ratio(core, c) >= cfg.group_similarity
                   for c in cluster):
                cluster.append(core); placed = True; break
        if not placed:
            merged.append([core])

    groups: list[ModelGroup] = []
    for cluster in merged:
        pairs = [(a, b) for a, b in combinations(cluster, 2)]
        conf = (sum(fuzz.token_set_ratio(a, b) for a, b in pairs) / len(pairs) / 100
                if pairs else 1.0)
        members = [GroupMember(r, n.role)
                   for c in cluster for (r, n) in buckets[c]]
        members.sort(key=lambda m: m.record.rel_path)
        title = max(cluster, key=len).replace("_", " ").title()
        groups.append(ModelGroup(members, title, _assembly(members), conf))

    if any(g.confidence < cfg.group_confidence_min for g in groups):
        all_members = [GroupMember(r, n.role) for r, n in normalized]
        all_members.sort(key=lambda m: m.record.rel_path)
        folder = Path(stl_records[0].rel_path).parent.name or "Ungrouped"
        return [ModelGroup(all_members, folder.replace("_", " ").title(),
                           "needs-review",
                           min(g.confidence for g in groups))]
    return sorted(groups, key=lambda g: g.title)
```

Also fix the `needs-review` case in `_assembly`: a multi-member group where every role is `model` means the cluster merged distinct-looking stems — that IS review-worthy; keep as written.

- [ ] **Step 4: Run tests to verify pass; iterate until the table passes.**
- [ ] **Step 5: Commit** — `git commit -m "feat: stem clustering with roles, assembly, group identity"`

---

### Task 7: Mesh facts

**Files:**
- Create: `src/stl_curator/meshfacts.py`
- Test: `tests/test_meshfacts.py`

**Interfaces:**
- Consumes: trimesh; `long_path` (Task 1).
- Produces: `MeshFacts` dataclass: `height_mm: float | None`, `triangles: int | None`, `watertight: bool | None`, `error: str | None`; `extract_mesh_facts(path: Path) -> MeshFacts`. Height = Z-extent of bounding box. Any exception from trimesh → `MeshFacts(None, None, None, error=str(e))` — never raises (spec §6).

- [ ] **Step 1: Write the failing tests**

`tests/test_meshfacts.py`:

```python
from pathlib import Path
import pytest
import trimesh
from stl_curator.meshfacts import MeshFacts, extract_mesh_facts


@pytest.fixture
def box_stl(tmp_path) -> Path:
    p = tmp_path / "box.stl"
    trimesh.creation.box(extents=[10.0, 20.0, 48.5]).export(p)
    return p


def test_height_is_z_extent(box_stl):
    facts = extract_mesh_facts(box_stl)
    assert facts.error is None
    assert facts.height_mm == pytest.approx(48.5)


def test_box_facts(box_stl):
    facts = extract_mesh_facts(box_stl)
    assert facts.triangles == 12
    assert facts.watertight is True


def test_corrupt_file_returns_error_not_raise(tmp_path):
    p = tmp_path / "bad.stl"
    p.write_bytes(b"not a mesh at all")
    facts = extract_mesh_facts(p)
    assert facts.height_mm is None
    assert facts.error
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement `src/stl_curator/meshfacts.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

import trimesh


@dataclass
class MeshFacts:
    height_mm: float | None
    triangles: int | None
    watertight: bool | None
    error: str | None = None


def extract_mesh_facts(path: Path) -> MeshFacts:
    try:
        mesh = trimesh.load(str(path), force="mesh")
        if mesh.is_empty or len(mesh.faces) == 0:
            return MeshFacts(None, None, None, "empty mesh")
        lo, hi = mesh.bounds
        return MeshFacts(float(hi[2] - lo[2]), int(len(mesh.faces)),
                         bool(mesh.is_watertight), None)
    except Exception as e:  # noqa: BLE001 — spec §6: errors never halt ingest
        return MeshFacts(None, None, None, str(e))
```

- [ ] **Step 4: Run tests, ruff.**
- [ ] **Step 5: Commit** — `git commit -m "feat: mesh facts extraction with error capture"`

---

### Task 8: Thumbnail harvesting

**Files:**
- Create: `src/stl_curator/thumbs.py` (harvest half)
- Test: `tests/test_thumbs_harvest.py`

**Interfaces:**
- Consumes: `FileRecord`, `IMAGE_EXTS` (Task 2); Pillow.
- Produces:
  - `score_image_candidate(rec: FileRecord) -> float` — base score = pixel count is unavailable pre-open, so: `size` bytes as proxy, then multipliers by filename: contains `render|preview|beauty|box|art|cover|hero` → ×3; contains `support|instruction|assembly|diagram|guide|chitubox|lychee` → ×0.1.
  - `pick_group_image(group_members_dir_images: list[FileRecord]) -> FileRecord | None` — highest score; `None` if list empty.
  - `thumb_path(thumbs_dir: Path, group_id: str) -> Path` = `thumbs_dir / group_id[:2] / f"{group_id}.webp"`.
  - `normalize_to_webp(src_image: Path, dest: Path, max_px: int = 512) -> None` — open with Pillow, `thumbnail((max_px, max_px))`, save webp quality 80, create parent dirs.

- [ ] **Step 1: Write the failing tests**

`tests/test_thumbs_harvest.py`:

```python
from pathlib import Path
import pytest
from PIL import Image
from stl_curator.scan import FileRecord
from stl_curator.thumbs import (normalize_to_webp, pick_group_image,
                                score_image_candidate, thumb_path)


def img_rec(name, size=1000):
    return FileRecord(f"C/R/{name}", Path(name), f"h_{name}", size, 1.0, "image")


@pytest.mark.parametrize("better,worse", [
    (img_rec("render.png", 1000), img_rec("photo.png", 1000)),
    (img_rec("preview.jpg", 500), img_rec("supports_guide.png", 5000)),
    (img_rec("big.png", 9000), img_rec("small.png", 100)),
    (img_rec("box_art.png", 1000), img_rec("assembly_diagram.png", 1000)),
])
def test_scoring_prefers(better, worse):
    assert score_image_candidate(better) > score_image_candidate(worse)


def test_pick_none_when_empty():
    assert pick_group_image([]) is None


def test_thumb_path_content_addressed(tmp_path):
    assert thumb_path(tmp_path, "g7f3a2c1") == tmp_path / "g7" / "g7f3a2c1.webp"


def test_normalize_to_webp(tmp_path):
    src = tmp_path / "big.png"
    Image.new("RGB", (1024, 768), "red").save(src)
    dest = tmp_path / "out" / "x.webp"
    normalize_to_webp(src, dest)
    with Image.open(dest) as im:
        assert im.format == "WEBP"
        assert max(im.size) <= 512
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement harvest half of `src/stl_curator/thumbs.py`**

```python
from __future__ import annotations
import re
from pathlib import Path

from PIL import Image

from stl_curator.scan import FileRecord

_GOOD = re.compile(r"render|preview|beauty|box|art|cover|hero", re.I)
_BAD = re.compile(r"support|instruction|assembly|diagram|guide|chitubox|lychee", re.I)


def score_image_candidate(rec: FileRecord) -> float:
    score = float(rec.size)
    name = Path(rec.rel_path).name
    if _GOOD.search(name):
        score *= 3
    if _BAD.search(name):
        score *= 0.1
    return score


def pick_group_image(candidates: list[FileRecord]) -> FileRecord | None:
    if not candidates:
        return None
    return max(candidates, key=score_image_candidate)


def thumb_path(thumbs_dir: Path, group_id: str) -> Path:
    return thumbs_dir / group_id[:2] / f"{group_id}.webp"


def normalize_to_webp(src_image: Path, dest: Path, max_px: int = 512) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src_image) as im:
        im = im.convert("RGB")
        im.thumbnail((max_px, max_px))
        im.save(dest, "WEBP", quality=80)
```

- [ ] **Step 4: Run tests, ruff.**
- [ ] **Step 5: Commit** — `git commit -m "feat: harvest-first thumbnail selection and webp normalization"`

---

### Task 9: Rendered thumbnail fallback

**Files:**
- Modify: `src/stl_curator/thumbs.py` (render half)
- Test: `tests/test_thumbs_render.py`

**Interfaces:**
- Consumes: trimesh, numpy, Pillow; `normalize_to_webp` (Task 8).
- Produces: `render_thumbnail(stl_path: Path, dest: Path, size_px: int = 512) -> bool` — deterministic offscreen render to webp at `dest`; returns `False` (never raises) when no GL backend works. Implementation order: try `pyrender` OffscreenRenderer with fixed ¾ camera and two fixed directional lights; on any exception fall back to `trimesh.Scene.save_image` with the same fixed camera transform; on failure return False. Camera: scene fit via `scene.camera_transform` computed from mesh bounds — azimuth 45°, elevation 30°, distance = 2.2 × bounding-sphere radius. No randomness anywhere.
- `render_available() -> bool` — cached probe: attempts a 8×8 render of a unit box; used by tests to skip and by pipeline to decide `missing` vs `rendered`.

- [ ] **Step 1: Write the failing tests**

`tests/test_thumbs_render.py`:

```python
from pathlib import Path
import pytest
import trimesh
from stl_curator.thumbs import render_available, render_thumbnail

pytestmark = pytest.mark.skipif(not render_available(),
                                reason="no offscreen GL backend on this machine")


@pytest.fixture
def cone_stl(tmp_path) -> Path:
    p = tmp_path / "cone.stl"
    trimesh.creation.cone(radius=5.0, height=20.0).export(p)
    return p


def test_render_produces_webp(cone_stl, tmp_path):
    dest = tmp_path / "t" / "x.webp"
    assert render_thumbnail(cone_stl, dest) is True
    assert dest.exists() and dest.stat().st_size > 0


def test_render_is_deterministic(cone_stl, tmp_path):
    a, b = tmp_path / "a.webp", tmp_path / "b.webp"
    render_thumbnail(cone_stl, a)
    render_thumbnail(cone_stl, b)
    assert a.read_bytes() == b.read_bytes()


def test_render_failure_returns_false(tmp_path):
    bad = tmp_path / "bad.stl"
    bad.write_bytes(b"junk")
    assert render_thumbnail(bad, tmp_path / "out.webp") is False
```

- [ ] **Step 2: Run to verify failure** (or skip — if `render_available()` is False on this machine, the suite skips: that is acceptable; note it in the task report. **If it skips, still verify `test_render_failure_returns_false` logic via the no-backend path returning False.**)

- [ ] **Step 3: Implement render half (append to `src/stl_curator/thumbs.py`)**

```python
import io
from functools import lru_cache

import numpy as np
import trimesh


def _camera_transform(mesh: trimesh.Trimesh) -> np.ndarray:
    center = mesh.bounds.mean(axis=0)
    radius = float(np.linalg.norm(mesh.bounds[1] - mesh.bounds[0])) / 2 or 1.0
    az, el = np.radians(45.0), np.radians(30.0)
    dist = 2.2 * radius
    eye = center + dist * np.array(
        [np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)])
    fwd = (center - eye); fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0, 0, 1.0]); right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    m = np.eye(4)
    m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = right, up, -fwd, eye
    return m


def _render_pyrender(mesh: trimesh.Trimesh, size_px: int) -> "np.ndarray":
    import pyrender
    scene = pyrender.Scene(bg_color=[240, 240, 240, 255],
                           ambient_light=[0.3, 0.3, 0.3])
    scene.add(pyrender.Mesh.from_trimesh(mesh, smooth=False))
    cam = pyrender.PerspectiveCamera(yfov=np.radians(45.0))
    pose = _camera_transform(mesh)
    scene.add(cam, pose=pose)
    light = pyrender.DirectionalLight(intensity=3.0)
    scene.add(light, pose=pose)
    r = pyrender.OffscreenRenderer(size_px, size_px)
    try:
        color, _ = r.render(scene)
    finally:
        r.delete()
    return color


def render_thumbnail(stl_path: Path, dest: Path, size_px: int = 512) -> bool:
    try:
        mesh = trimesh.load(str(stl_path), force="mesh")
        if mesh.is_empty or len(mesh.faces) == 0:
            return False
    except Exception:
        return False
    png_bytes: bytes | None = None
    try:
        color = _render_pyrender(mesh, size_px)
        from PIL import Image as _Image
        buf = io.BytesIO()
        _Image.fromarray(color).save(buf, "PNG")
        png_bytes = buf.getvalue()
    except Exception:
        try:
            scene = trimesh.Scene(mesh)
            scene.camera_transform = _camera_transform(mesh)
            png_bytes = scene.save_image(resolution=(size_px, size_px))
        except Exception:
            return False
    if not png_bytes:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_png = dest.with_suffix(".tmp.png")
    tmp_png.write_bytes(png_bytes)
    try:
        normalize_to_webp(tmp_png, dest)
    finally:
        tmp_png.unlink(missing_ok=True)
    return True


@lru_cache(maxsize=1)
def render_available() -> bool:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "probe.stl"
        trimesh.creation.box(extents=[1, 1, 1]).export(p)
        return render_thumbnail(p, Path(td) / "probe.webp", size_px=8)
```

- [ ] **Step 4: Run tests.** If pyrender fails on this Windows machine but trimesh save_image works, that's fine (fallback covers it). **If BOTH backends fail** (`render_available()` False): STOP and raise a problem brief to the user per their standing instruction — options: (a) pin `pyglet<2` (trimesh save_image needs it) — pro: quick, con: dependency pin; (b) osmesa/EGL wheel for pyrender — pro: robust headless, con: Windows setup pain; (c) ship M1 with `missing` thumbs for unharvestable groups — pro: zero work now, con: some noteless art. Continue with remaining tasks while awaiting the answer; thumbnails degrade to `missing`.

- [ ] **Step 5: Commit** — `git commit -m "feat: deterministic render fallback for thumbnails"`

---

### Task 10: Frontmatter merge engine

**Files:**
- Create: `src/stl_curator/vault.py` (merge half)
- Test: `tests/test_merge.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `MACHINE_FIELDS = {"id", "thumb", "thumbs_all", "height_mm", "group_confidence", "mesh_error", "paths_root", "type"}`
  - `HUMAN_FIELDS = {"status", "tags", "title", "creator", "campaign", "assembly", "source", "mmf_id"}` (human wins once set; pipeline may only fill when absent)
  - `merge_frontmatter(existing: dict | None, generated: dict) -> dict`:
    - `existing is None` → return `generated` unchanged.
    - Machine fields: generated value always wins.
    - Human fields: existing value wins when key present in existing (even if falsy-but-set, e.g. empty tags list); generated fills gaps.
    - Unknown keys present only in existing (human-added) are preserved.
    - `files`: merged per-hash by `merge_files_list`.
  - `merge_files_list(existing: list[dict] | None, generated: list[dict]) -> list[dict]` — for each generated entry (keyed by `hash`): if an existing entry with same hash exists, keep its `role` (human-owned) and any `footprint` value if generated lacks one; take generated `path` (machine fact — file may have moved). Existing entries whose hash is NOT in generated are preserved (human moved a file into this note; membership is human-owned). Order: existing order first, then new hashes sorted by path.

- [ ] **Step 1: Write the failing tests**

`tests/test_merge.py`:

```python
import pytest
from stl_curator.vault import merge_files_list, merge_frontmatter


GEN = {
    "id": "g1", "type": "model", "title": "Goblin", "status": "unprinted",
    "tags": ["needs-review"], "assembly": "variants", "height_mm": 30.0,
    "group_confidence": 0.9,
    "files": [{"path": "C/R/g1.stl", "hash": "h1", "role": "variant"}],
}


def test_no_existing_returns_generated():
    assert merge_frontmatter(None, dict(GEN)) == GEN


@pytest.mark.parametrize("field,human_value", [
    ("status", "painted"),
    ("tags", ["goblinoid", "32mm"]),
    ("title", "Goblin Warband"),
    ("assembly", "multipart"),
    ("creator", "[[GoblinCo]]"),
])
def test_human_fields_survive(field, human_value):
    existing = dict(GEN, **{field: human_value})
    merged = merge_frontmatter(existing, dict(GEN))
    assert merged[field] == human_value


@pytest.mark.parametrize("field,new_value", [
    ("height_mm", 99.9),
    ("group_confidence", 0.4),
    ("thumb", "thumbs/g1/new.webp"),
])
def test_machine_fields_update(field, new_value):
    existing = dict(GEN, thumb="thumbs/old.webp")
    merged = merge_frontmatter(existing, dict(GEN, **{field: new_value}))
    assert merged[field] == new_value


def test_unknown_human_keys_pass_through():
    existing = dict(GEN, my_notes="use for Thornwood")
    merged = merge_frontmatter(existing, dict(GEN))
    assert merged["my_notes"] == "use for Thornwood"


def test_empty_but_set_human_field_survives():
    existing = dict(GEN, tags=[])
    merged = merge_frontmatter(existing, dict(GEN))
    assert merged["tags"] == []


def test_files_role_kept_path_updated():
    existing = [{"path": "old/loc.stl", "hash": "h1", "role": "part"}]
    generated = [{"path": "new/loc.stl", "hash": "h1", "role": "variant"}]
    assert merge_files_list(existing, generated) == [
        {"path": "new/loc.stl", "hash": "h1", "role": "part"}]


def test_files_human_added_member_preserved():
    existing = [{"path": "a.stl", "hash": "h1", "role": "model"},
                {"path": "b.stl", "hash": "h2", "role": "part"}]
    generated = [{"path": "a.stl", "hash": "h1", "role": "model"}]
    merged = merge_files_list(existing, generated)
    assert {e["hash"] for e in merged} == {"h1", "h2"}


def test_files_footprint_preserved():
    existing = [{"path": "a.stl", "hash": "h1", "role": "model",
                 "footprint": "footprints/h1/h1.json"}]
    generated = [{"path": "a.stl", "hash": "h1", "role": "model"}]
    assert merge_files_list(existing, generated)[0]["footprint"] == \
        "footprints/h1/h1.json"
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement merge half of `src/stl_curator/vault.py`**

```python
from __future__ import annotations

MACHINE_FIELDS = {"id", "thumb", "thumbs_all", "height_mm", "group_confidence",
                  "mesh_error", "paths_root", "type"}
HUMAN_FIELDS = {"status", "tags", "title", "creator", "campaign", "assembly",
                "source", "mmf_id"}


def merge_files_list(existing, generated):
    existing = existing or []
    by_hash = {e["hash"]: dict(e) for e in existing}
    out = []
    seen = set()
    for e in existing:
        h = e["hash"]
        gen = next((g for g in generated if g["hash"] == h), None)
        entry = dict(e)
        if gen is not None:
            entry["path"] = gen["path"]                      # machine fact
            if "footprint" not in entry and "footprint" in gen:
                entry["footprint"] = gen["footprint"]
        out.append(entry); seen.add(h)
    new = [g for g in generated if g["hash"] not in seen]
    out.extend(sorted((dict(g) for g in new), key=lambda g: g["path"]))
    return out


def merge_frontmatter(existing: dict | None, generated: dict) -> dict:
    if existing is None:
        return generated
    merged = dict(existing)                                   # human keys survive
    for k, v in generated.items():
        if k == "files":
            merged["files"] = merge_files_list(existing.get("files"), v)
        elif k in MACHINE_FIELDS:
            merged[k] = v
        elif k in HUMAN_FIELDS:
            if k not in existing:
                merged[k] = v
        else:
            merged.setdefault(k, v)
    return merged
```

- [ ] **Step 4: Run tests, ruff.** This suite is the project's most important (founding decision: never clobber human edits) — do not weaken any case to make it pass.
- [ ] **Step 5: Commit** — `git commit -m "feat: merge engine — human fields never clobbered"`

---

### Task 11: Vault note writer and entity stubs

**Files:**
- Modify: `src/stl_curator/vault.py`
- Test: `tests/test_vault_write.py`

**Interfaces:**
- Consumes: `ModelGroup` (Task 6), `Config` (Task 1), `merge_frontmatter` (Task 10), `python-frontmatter`, `MeshFacts` per hash via dict, thumb path.
- Produces:
  - `slugify(text: str) -> str` — lowercase, spaces/underscores→`-`, strip non `[a-z0-9-]`, collapse `-`.
  - `note_path(vault_dir: Path, creator: str, title: str) -> Path` = `vault_dir/models/{slugify(creator)}--{slugify(title)}.md`.
  - `infer_creator_campaign(rel_path: str) -> tuple[str, str | None]` — first path segment = creator; second = campaign when the file sits ≥2 levels deep, else None.
  - `build_frontmatter(group: ModelGroup, cfg: Config, facts_by_hash: dict[str, "MeshFacts"], thumb_rel: str | None, footprints_dir_name: str = "footprints") -> dict` — assembles schema v1.1 (spec §3): `files[].footprint` = `f"{footprints_dir_name}/{h[:2]}/{h}.json"` (reserved pointer — written whether or not the file exists yet, it's a content-addressed *location*, per spec §4); `height_mm` = max member height (None-safe); `mesh_error: true` if any member facts has error; `tags` starts `["needs-review"]` iff `group.assembly == "needs-review"` or confidence < cfg.group_confidence_min else `[]`; `status: "unprinted"`; `source` = `"patreon"|"kickstarter"|"mmf"` if those words appear in the rel_path (case-insensitive) else `"other"`; `mmf_id: None`.
  - `write_model_note(path: Path, generated_fm: dict, title: str) -> str` — returns `"created" | "updated" | "unchanged"`. Loads existing note via `frontmatter.load` when present, merges, writes ONLY if the merged frontmatter differs from existing. Body on create: `# {title}\n\n> Auto-generated stub. Notes below this line are yours; the pipeline never touches body text.\n`. Body on update: untouched, verbatim.
  - `ensure_entity_note(vault_dir: Path, kind: str, name: str) -> bool` (`kind` in `"creators" | "campaigns"`; True if created). Creator body includes the two Dataview blocks from spec §3; campaign body includes a models table filtered by campaign. Never overwrites an existing entity note.
  - `write_vault_config(vault_dir: Path) -> None` — writes `vault_dir/.obsidian/app.json` = `{}` and `community-plugins.json` = `["dataview"]` only if `.obsidian/` absent.

- [ ] **Step 1: Write the failing tests**

`tests/test_vault_write.py`:

```python
from pathlib import Path
import frontmatter
import pytest
from stl_curator.config import Config
from stl_curator.grouping import GroupMember, ModelGroup
from stl_curator.meshfacts import MeshFacts
from stl_curator.scan import FileRecord
from stl_curator.vault import (build_frontmatter, ensure_entity_note,
                               infer_creator_campaign, note_path, slugify,
                               write_model_note)


@pytest.mark.parametrize("text,slug", [
    ("GoblinCo", "goblinco"),
    ("Owlbear, Large", "owlbear-large"),
    ("troll_king  2", "troll-king-2"),
])
def test_slugify(text, slug):
    assert slugify(text) == slug


@pytest.mark.parametrize("rel,creator,campaign", [
    ("GoblinCo/2024-03/kit/goblin.stl", "GoblinCo", "2024-03"),
    ("GoblinCo/goblin.stl", "GoblinCo", None),
])
def test_infer_creator_campaign(rel, creator, campaign):
    assert infer_creator_campaign(rel) == (creator, campaign)


def make_group():
    rec = FileRecord("GoblinCo/2024-03/goblin_pose1.stl", Path("x"), "aabbccdd" * 8,
                     1, 1.0, "stl")
    return ModelGroup([GroupMember(rec, "variant")], "Goblin", "variants", 0.95)


def cfg(tmp_path):
    return Config(store_root=tmp_path, vault_dir=tmp_path / "vault",
                  thumbs_dir=tmp_path / "thumbs",
                  footprints_dir=tmp_path / "footprints",
                  cache_db=tmp_path / "c.db")


def test_build_frontmatter_schema(tmp_path):
    fm = build_frontmatter(make_group(), cfg(tmp_path),
                           {"aabbccdd" * 8: MeshFacts(30.0, 100, True)},
                           thumb_rel="thumbs/xx/x.webp")
    assert fm["type"] == "model"
    assert fm["creator"] == "[[GoblinCo]]"
    assert fm["campaign"] == "[[GoblinCo 2024-03]]"
    assert fm["source"] == "other"
    assert fm["height_mm"] == 30.0
    assert fm["files"][0]["footprint"].startswith("footprints/aa/")
    assert fm["status"] == "unprinted"


def test_write_then_rewrite_unchanged(tmp_path):
    p = tmp_path / "vault" / "models" / "n.md"
    fm = {"id": "g1", "type": "model", "title": "Goblin", "status": "unprinted"}
    assert write_model_note(p, dict(fm), "Goblin") == "created"
    assert write_model_note(p, dict(fm), "Goblin") == "unchanged"


def test_rewrite_preserves_body_and_human_fields(tmp_path):
    p = tmp_path / "vault" / "models" / "n.md"
    write_model_note(p, {"id": "g1", "type": "model", "status": "unprinted"}, "G")
    note = frontmatter.load(p)
    note["status"] = "painted"
    note.content += "\nMy campaign notes."
    with open(p, "wb") as f:
        frontmatter.dump(note, f)
    result = write_model_note(p, {"id": "g1", "type": "model",
                                  "status": "unprinted", "height_mm": 5.0}, "G")
    assert result == "updated"
    out = frontmatter.load(p)
    assert out["status"] == "painted"
    assert out["height_mm"] == 5.0
    assert "My campaign notes." in out.content


def test_entity_note_created_once(tmp_path):
    assert ensure_entity_note(tmp_path / "vault", "creators", "GoblinCo") is True
    assert ensure_entity_note(tmp_path / "vault", "creators", "GoblinCo") is False
    text = (tmp_path / "vault" / "creators" / "GoblinCo.md").read_text(encoding="utf-8")
    assert "dataview" in text and "[[GoblinCo]]" in text
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement (append to `src/stl_curator/vault.py`)**

```python
import re
from pathlib import Path

import frontmatter

from stl_curator.config import Config
from stl_curator.grouping import ModelGroup
from stl_curator.meshfacts import MeshFacts


def slugify(text: str) -> str:
    s = re.sub(r"[ _]+", "-", text.strip().lower())
    s = re.sub(r"[^a-z0-9-]", "", s)
    return re.sub(r"-{2,}", "-", s).strip("-")


def note_path(vault_dir: Path, creator: str, title: str) -> Path:
    return vault_dir / "models" / f"{slugify(creator)}--{slugify(title)}.md"


def infer_creator_campaign(rel_path: str) -> tuple[str, str | None]:
    parts = Path(rel_path).parts
    creator = parts[0] if parts else "Unknown"
    campaign = parts[1] if len(parts) >= 3 else None
    return creator, campaign


_SOURCE_RE = re.compile(r"(patreon|kickstarter|mmf)", re.I)


def build_frontmatter(group: ModelGroup, cfg: Config,
                      facts_by_hash: dict[str, MeshFacts],
                      thumb_rel: str | None,
                      footprints_dir_name: str = "footprints") -> dict:
    first_rel = group.members[0].record.rel_path
    creator, campaign = infer_creator_campaign(first_rel)
    files = []
    heights, any_err = [], False
    for m in group.members:
        h = m.record.hash
        facts = facts_by_hash.get(h)
        if facts:
            any_err = any_err or bool(facts.error)
            if facts.height_mm is not None:
                heights.append(facts.height_mm)
        files.append({
            "path": m.record.rel_path, "hash": h, "role": m.role,
            "footprint": f"{footprints_dir_name}/{h[:2]}/{h}.json",
        })
    src = _SOURCE_RE.search(first_rel)
    review = group.assembly == "needs-review" or \
        group.confidence < cfg.group_confidence_min
    fm = {
        "id": group.id, "type": "model", "title": group.title,
        "creator": f"[[{creator}]]",
        "campaign": f"[[{creator} {campaign}]]" if campaign else None,
        "files": files, "assembly": group.assembly,
        "thumb": thumb_rel, "thumbs_all": [],
        "height_mm": max(heights) if heights else None,
        "group_confidence": round(group.confidence, 2),
        "tags": ["needs-review"] if review else [],
        "status": "unprinted",
        "source": src.group(1).lower() if src else "other",
        "mmf_id": None,
        "paths_root": str(cfg.store_root),
    }
    if any_err:
        fm["mesh_error"] = True
    return fm


def write_model_note(path: Path, generated_fm: dict, title: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        note = frontmatter.load(path)
        merged = merge_frontmatter(dict(note.metadata), generated_fm)
        if merged == dict(note.metadata):
            return "unchanged"
        note.metadata = merged
        with open(path, "wb") as f:
            frontmatter.dump(note, f)
        return "updated"
    note = frontmatter.Post(
        f"# {title}\n\n> Auto-generated stub. Notes below this line are yours; "
        "the pipeline never touches body text.\n", **generated_fm)
    with open(path, "wb") as f:
        frontmatter.dump(note, f)
    return "created"


_CREATOR_BODY = """# {name}

## Campaigns
```dataview
LIST FROM "campaigns" WHERE creator = [[{name}]]
```

## Models
```dataview
TABLE thumb, status FROM "models" WHERE creator = [[{name}]]
```
"""

_CAMPAIGN_BODY = """# {name}

## Models
```dataview
TABLE thumb, status FROM "models" WHERE campaign = [[{name}]]
```
"""


def ensure_entity_note(vault_dir: Path, kind: str, name: str) -> bool:
    path = vault_dir / kind / f"{name}.md"
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    body = _CREATOR_BODY if kind == "creators" else _CAMPAIGN_BODY
    meta = {"type": "creator" if kind == "creators" else "campaign"}
    if kind == "campaigns":
        meta["creator"] = f"[[{name.split(' ')[0]}]]"
    note = frontmatter.Post(body.format(name=name), **meta)
    with open(path, "wb") as f:
        frontmatter.dump(note, f)
    return True


def write_vault_config(vault_dir: Path) -> None:
    ob = vault_dir / ".obsidian"
    if ob.exists():
        return
    ob.mkdir(parents=True)
    (ob / "app.json").write_text("{}", encoding="utf-8")
    (ob / "community-plugins.json").write_text('["dataview"]', encoding="utf-8")
```

- [ ] **Step 4: Run tests, ruff.**
- [ ] **Step 5: Commit** — `git commit -m "feat: merge-aware vault notes and entity stubs"`

---

### Task 12: Reports

**Files:**
- Create: `src/stl_curator/reports.py`
- Test: `tests/test_reports.py`

**Interfaces:**
- Consumes: `Cache.duplicate_hashes()` (Task 3).
- Produces: `write_duplicate_report(duplicates: dict[str, list[str]], vault_dir: Path) -> Path` — writes `vault_dir/reports/duplicates.md` (markdown table: hash prefix, count, paths); `write_error_report(errors: list[tuple[str, str]], vault_dir: Path) -> Path` — `vault_dir/reports/errors.md` (path, message). Both fully regenerated each run (reports are machine-owned, not merge targets). Empty input still writes the file with "None found." so staleness is visible.

- [ ] **Step 1: Write the failing tests**

`tests/test_reports.py`:

```python
import pytest
from stl_curator.reports import write_duplicate_report, write_error_report


def test_duplicate_report_lists_paths(tmp_path):
    p = write_duplicate_report({"aabb" * 16: ["a.stl", "b/a.stl"]}, tmp_path)
    text = p.read_text(encoding="utf-8")
    assert p == tmp_path / "reports" / "duplicates.md"
    assert "aabbaabb" in text and "b/a.stl" in text


@pytest.mark.parametrize("writer,fname", [
    (write_duplicate_report, "duplicates.md"),
    (write_error_report, "errors.md"),
])
def test_empty_reports_written(tmp_path, writer, fname):
    p = writer({} if fname == "duplicates.md" else [], tmp_path)
    assert p.name == fname
    assert "None found" in p.read_text(encoding="utf-8")


def test_error_report(tmp_path):
    p = write_error_report([("C/bad.zip", "BadZipFile")], tmp_path)
    assert "C/bad.zip" in p.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement `src/stl_curator/reports.py`**

```python
from __future__ import annotations
from pathlib import Path


def _write(vault_dir: Path, name: str, lines: list[str]) -> Path:
    out = vault_dir / "reports" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def write_duplicate_report(duplicates: dict[str, list[str]], vault_dir: Path) -> Path:
    lines = ["# Duplicate Files", ""]
    if not duplicates:
        lines.append("None found.")
    else:
        lines += ["| hash | count | paths |", "|---|---|---|"]
        for h, paths in sorted(duplicates.items()):
            lines.append(f"| `{h[:8]}` | {len(paths)} | {' <br> '.join(paths)} |")
    return _write(vault_dir, "duplicates.md", lines)


def write_error_report(errors: list[tuple[str, str]], vault_dir: Path) -> Path:
    lines = ["# Ingest Errors", ""]
    if not errors:
        lines.append("None found.")
    else:
        lines += ["| path | error |", "|---|---|"]
        for rel, msg in errors:
            lines.append(f"| {rel} | {msg} |")
    return _write(vault_dir, "errors.md", lines)
```

- [ ] **Step 4: Run tests, ruff.**
- [ ] **Step 5: Commit** — `git commit -m "feat: duplicate and error reports"`

---

### Task 13: Ingest orchestrator, CLI, idempotency

**Files:**
- Create: `src/stl_curator/pipeline.py`, `src/stl_curator/cli.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `IngestSummary` dataclass: `files: int`, `groups: int`, `created: int`, `updated: int`, `unchanged: int`, `errors: int`, `needs_review: int`, `thumbs_harvested: int`, `thumbs_rendered: int`, `thumbs_missing: int`.
  - `ingest(cfg: Config, dry_run: bool = False) -> IngestSummary` — full pipeline per spec §5:
    1. scan; 2. extract zips (skip in dry_run), rescan if anything extracted; 3. upsert files into cache; 4. group per leaf folder (STLs only, `Path(rel).parent` as key), skipping groups whose every member hash is in `cache.claimed_hashes()`... **claimed hashes constrain regrouping: any auto-group containing a claimed hash drops those members** (they belong to human notes); 5. mesh facts per unique hash (cache hit skips recompute); 6. thumbnail per group: candidates = images in the same folder (+ same folder as the zip the folder came from) → harvest → else `render_thumbnail` on the first STL member → else missing; 7. `build_frontmatter` + `write_model_note` + `ensure_entity_note` (+`write_vault_config` once); 8. reports; 9. summary. In `dry_run`, steps 6–8 only count what they *would* do (no writes; `write_model_note` result predicted by loading + merging without dumping — implement via `plan_model_note(path, generated) -> str` helper in vault.py that does the merge and compares without writing).
  - CLI (`src/stl_curator/cli.py`): `typer.Typer()` named `app`; commands:
    - `ingest root: Path` (argument, optional — defaults to config `store_root`), options `--config PATH` (default `config.toml`), `--dry-run` flag. Prints summary table.
    - `rebuild-cache` with `--config PATH` — Task 14 wires body; in this task, stub that raises `typer.Exit(1)` with message "implemented in Task 14" is **not acceptable** — instead do not register the command yet.

- [ ] **Step 1: Write the failing tests**

`tests/test_pipeline.py`:

```python
import zipfile
from pathlib import Path
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
        z.writestr("owlbear.stl",
                   trimesh.creation.box(extents=[9, 9, 9]).export(file_type="stl"))
    # a duplicate
    (root / "GoblinCo" / "2024-03" / "troll_king_copy.stl").write_bytes(
        (kit / "troll_king.stl").read_bytes())
    return Config(store_root=root, vault_dir=tmp_path / "vault",
                  thumbs_dir=tmp_path / "thumbs",
                  footprints_dir=tmp_path / "footprints",
                  cache_db=tmp_path / "cache.db")


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
    assert any("owlbear" in p.name
               for p in (store.vault_dir / "models").glob("*.md"))


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
    with open(note, "wb") as f:
        frontmatter.dump(post, f)
    ingest(store)
    assert frontmatter.load(note)["status"] == "painted"
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement `src/stl_curator/pipeline.py`**

```python
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from stl_curator.cache import Cache
from stl_curator.config import Config
from stl_curator.grouping import ModelGroup, group_folder, load_vocab
from stl_curator.meshfacts import MeshFacts, extract_mesh_facts
from stl_curator.reports import write_duplicate_report, write_error_report
from stl_curator.scan import FileRecord, scan_store
from stl_curator.thumbs import (normalize_to_webp, pick_group_image,
                                render_thumbnail, thumb_path)
from stl_curator.vault import (build_frontmatter, ensure_entity_note,
                               infer_creator_campaign, note_path,
                               plan_model_note, write_model_note,
                               write_vault_config)
from stl_curator.zips import extract_needed_zips


@dataclass
class IngestSummary:
    files: int = 0
    groups: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    errors: int = 0
    needs_review: int = 0
    thumbs_harvested: int = 0
    thumbs_rendered: int = 0
    thumbs_missing: int = 0


def _mesh_facts_cached(cache: Cache, rec: FileRecord) -> MeshFacts:
    row = cache.get_mesh_facts(rec.hash)
    if row is not None:
        return MeshFacts(row["height_mm"], row["triangles"],
                         None if row["watertight"] is None else bool(row["watertight"]),
                         row["error"])
    facts = extract_mesh_facts(rec.abs_path)
    cache.set_mesh_facts(rec.hash, facts.height_mm, facts.triangles,
                         facts.watertight, facts.error)
    return facts


def _ensure_thumb(group: ModelGroup, images: list[FileRecord], cfg: Config,
                  cache: Cache, dry_run: bool, summary: IngestSummary) -> str | None:
    dest = thumb_path(cfg.thumbs_dir, group.id)
    rel = f"{cfg.thumbs_dir.name}/{group.id[:2]}/{group.id}.webp"
    if dest.exists():
        return rel
    pick = pick_group_image(images)
    if pick is not None:
        summary.thumbs_harvested += 1
        if not dry_run:
            normalize_to_webp(pick.abs_path, dest)
            cache.set_thumb(group.id, "harvested")
        return rel
    first_stl = group.members[0].record.abs_path
    if dry_run:
        summary.thumbs_rendered += 1   # optimistic count; dry-run doesn't probe GL
        return rel
    if render_thumbnail(first_stl, dest):
        summary.thumbs_rendered += 1
        cache.set_thumb(group.id, "rendered")
        return rel
    summary.thumbs_missing += 1
    cache.set_thumb(group.id, "missing")
    return None


def ingest(cfg: Config, dry_run: bool = False) -> IngestSummary:
    summary = IngestSummary()
    errors: list[tuple[str, str]] = []
    vocab = load_vocab()
    records = scan_store(cfg.store_root)
    if not dry_run:
        zres = extract_needed_zips(records, cfg.store_root)
        errors.extend(zres.errors)
        if zres.extracted:
            records = scan_store(cfg.store_root)
    summary.files = len(records)

    cache = Cache(cfg.cache_db if not dry_run else Path(":memory:"))
    for rec in records:
        cache.upsert_file(rec)
    claimed = cache.claimed_hashes()

    by_folder: dict[str, list[FileRecord]] = defaultdict(list)
    images_by_folder: dict[str, list[FileRecord]] = defaultdict(list)
    for rec in records:
        folder = str(Path(rec.rel_path).parent)
        if rec.kind == "stl":
            by_folder[folder].append(rec)
        elif rec.kind == "image":
            images_by_folder[folder].append(rec)

    if not dry_run:
        cfg.vault_dir.mkdir(parents=True, exist_ok=True)
        write_vault_config(cfg.vault_dir)

    for folder in sorted(by_folder):
        stls = [r for r in by_folder[folder] if r.hash not in claimed]
        for group in group_folder(stls, vocab, cfg):
            summary.groups += 1
            if group.assembly == "needs-review":
                summary.needs_review += 1
            facts = {m.record.hash: _mesh_facts_cached(cache, m.record)
                     for m in group.members}
            for h, f in facts.items():
                if f.error:
                    errors.append((next(m.record.rel_path for m in group.members
                                        if m.record.hash == h), f.error))
            thumb_rel = _ensure_thumb(group, images_by_folder.get(folder, []),
                                      cfg, cache, dry_run, summary)
            fm = build_frontmatter(group, cfg, facts, thumb_rel,
                                   footprints_dir_name=cfg.footprints_dir.name)
            creator, campaign = infer_creator_campaign(group.members[0].record.rel_path)
            npath = note_path(cfg.vault_dir, creator, group.title)
            if dry_run:
                result = plan_model_note(npath, fm)
            else:
                result = write_model_note(npath, fm, group.title)
                cache.upsert_group(group.id, [m.record.hash for m in group.members],
                                   group.confidence)
                ensure_entity_note(cfg.vault_dir, "creators", creator)
                if campaign:
                    ensure_entity_note(cfg.vault_dir, "campaigns",
                                       f"{creator} {campaign}")
            setattr(summary, {"created": "created", "updated": "updated",
                              "unchanged": "unchanged"}[result],
                    getattr(summary, result) + 1)

    summary.errors = len(errors)
    if not dry_run:
        write_duplicate_report(cache.duplicate_hashes(), cfg.vault_dir)
        write_error_report(errors, cfg.vault_dir)
    cache.close()
    return summary
```

Add `plan_model_note` to `src/stl_curator/vault.py`:

```python
def plan_model_note(path: Path, generated_fm: dict) -> str:
    if not path.exists():
        return "created"
    note = frontmatter.load(path)
    merged = merge_frontmatter(dict(note.metadata), generated_fm)
    return "unchanged" if merged == dict(note.metadata) else "updated"
```

Implement `src/stl_curator/cli.py`:

```python
from __future__ import annotations
from pathlib import Path

import typer

from stl_curator.config import load_config
from stl_curator.pipeline import ingest as run_ingest

app = typer.Typer(help="STL library curator")


@app.command()
def ingest(
    root: Path | None = typer.Argument(None, help="Store root (default: config)"),
    config: Path = typer.Option(Path("config.toml"), "--config"),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    cfg = load_config(config, store_root=root)
    s = run_ingest(cfg, dry_run=dry_run)
    for k, v in vars(s).items():
        typer.echo(f"{k:18} {v}")


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run the full suite** — `uv run pytest -v`. The idempotency and human-edit tests are the acceptance gate (spec §6, §7.5). Also run `uv run stl-curator ingest --help` to smoke the CLI.
- [ ] **Step 5: Commit** — `git commit -m "feat: ingest pipeline, CLI, idempotent end-to-end"`

---

### Task 14: rebuild-cache command

**Files:**
- Modify: `src/stl_curator/pipeline.py`, `src/stl_curator/cli.py`
- Test: `tests/test_rebuild.py`

**Interfaces:**
- Consumes: `Cache.clear()` (Task 3), `scan_store`, `frontmatter`.
- Produces: `rebuild_cache(cfg: Config) -> int` in `pipeline.py` — clears cache; rescans store (upserting files + recomputing mesh facts lazily is NOT needed — facts recompute on next ingest); re-reads every `vault_dir/models/*.md` note: for each, `upsert_group(fm["id"], [f["hash"] for f in fm["files"]], fm.get("group_confidence", 1.0), human_claimed=True)` — **all groups read back from the vault are marked human-claimed** because the vault is the curated source of truth; returns count of notes restored. CLI command `rebuild-cache` with `--config` prints "restored N groups from vault".

- [ ] **Step 1: Write the failing tests**

`tests/test_rebuild.py`:

```python
from pathlib import Path
import pytest
import trimesh
from stl_curator.cache import Cache
from stl_curator.config import Config
from stl_curator.pipeline import ingest, rebuild_cache


@pytest.fixture
def cfg(tmp_path) -> Config:
    root = tmp_path / "store"
    (root / "C" / "R").mkdir(parents=True)
    trimesh.creation.box(extents=[5, 5, 30]).export(root / "C" / "R" / "orc.stl")
    return Config(store_root=root, vault_dir=tmp_path / "vault",
                  thumbs_dir=tmp_path / "thumbs",
                  footprints_dir=tmp_path / "footprints",
                  cache_db=tmp_path / "cache.db")


def test_rebuild_restores_groups_as_claimed(cfg):
    ingest(cfg)
    cfg.cache_db.unlink()          # simulate cache loss
    n = rebuild_cache(cfg)
    assert n == 1
    cache = Cache(cfg.cache_db)
    assert len(cache.claimed_hashes()) == 1
    cache.close()


def test_ingest_after_rebuild_is_noop(cfg):
    ingest(cfg)
    cfg.cache_db.unlink()
    rebuild_cache(cfg)
    s = ingest(cfg)
    assert (s.created, s.updated) == (0, 0)
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement** — append to `pipeline.py`:

```python
import frontmatter as _frontmatter


def rebuild_cache(cfg: Config) -> int:
    cache = Cache(cfg.cache_db)
    cache.clear()
    for rec in scan_store(cfg.store_root):
        cache.upsert_file(rec)
    restored = 0
    models_dir = cfg.vault_dir / "models"
    if models_dir.exists():
        for note_file in sorted(models_dir.glob("*.md")):
            fm = _frontmatter.load(note_file).metadata
            files = fm.get("files") or []
            if fm.get("id") and files:
                cache.upsert_group(fm["id"], [f["hash"] for f in files],
                                   fm.get("group_confidence", 1.0),
                                   human_claimed=True)
                restored += 1
    cache.close()
    return restored
```

Append to `cli.py`:

```python
@app.command("rebuild-cache")
def rebuild(config: Path = typer.Option(Path("config.toml"), "--config")):
    cfg = load_config(config)
    n = rebuild_cache_fn(cfg)
    typer.echo(f"restored {n} groups from vault")
```

(with `from stl_curator.pipeline import rebuild_cache as rebuild_cache_fn` added to the imports).

**Note the design consequence encoded in the first test:** after a rebuild, ALL vault groups are human-claimed, so a following ingest must be a no-op (claimed members are excluded from regrouping, and their notes already exist). This is the "no state lives only in SQLite" founding decision made testable.

- [ ] **Step 4: Run the full suite** — `uv run pytest -v` — everything green; `uv run ruff check` clean.
- [ ] **Step 5: Commit** — `git commit -m "feat: rebuild-cache from disk + vault frontmatter"`

---

### Task 15: Wire-up run against example_stls and work log

**Files:**
- Create: `config.toml` (from example, pointing at `example_stls/`) — gitignored, so also verify `config.example.toml` matches
- Modify: `docs/project_notes/issues.md`, `docs/project_notes/key_facts.md` (commands section if reality diverged)

**Interfaces:** none — this is the verification task.

- [ ] **Step 1: Real run** — `uv run stl-curator ingest --config config.toml` against `example_stls/` (if the user has dropped files in; if still empty, run against a synthetic tree created under the scratchpad and say so in the report).
- [ ] **Step 2: Verify acceptance criteria** — second run reports `created 0, updated 0`; `--dry-run` on a fresh clone-like state predicts creations without writing; open-in-Obsidian sanity check is the USER's step — surface the vault path and what to look at.
- [ ] **Step 3: Log completion** in `docs/project_notes/issues.md` (entry `SETUP-002: M1 ingest spine implemented`) and record any deviations in `docs/project_notes/decisions.md` if a spec decision changed during implementation (with the why).
- [ ] **Step 4: Commit** — `git commit -m "chore: M1 wire-up, work log"`

---

## Self-Review Notes (completed)

- **Spec coverage:** §2 layout → T1/T11/T13; §3 schema+merge → T10/T11; §4 packer contract → footprint pointers in T11 (`build_frontmatter`), preservation in T10; §5 pipeline stages 1–7 → T2/T4/T5+T6/T7/T8+T9/T11/T12+T13; §6 config/cache/errors/dry-run → T1/T3/T13/T14; §7 test priorities 1–5 → T10 / T5+T6 / T6 / T9+T8 / T13.
- **Not covered deliberately:** MMF anything (M2), footprint JSON generation (plate_packer's side), file renaming (deferred), rclone automation (v2 per seed roadmap).
- **Type consistency check:** `FileRecord(rel_path, abs_path, hash, size, mtime, kind)` used identically in T2–T13; `group_id` 8-hex in T6, consumed by `thumb_path`/`build_frontmatter`; `MeshFacts` fields match between T7 and T11/T13; `write_model_note` returns `created|updated|unchanged` consumed by T13 summary mapping.
- **Known judgment calls encoded:** dry-run uses `:memory:` cache (predictions only, zero disk writes); rebuild marks all vault groups human-claimed; needs-review collapse keeps folders coarse.
