from __future__ import annotations

import hashlib
import re
import tomllib
from dataclasses import dataclass, field
from importlib import resources
from itertools import combinations
from pathlib import Path

from rapidfuzz import fuzz

from stl_curator.config import Config
from stl_curator.scan import FileRecord

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
            if nxt in vocab.part_words:  # wing_l, tail_01 → bind to part
                tokens.pop()
                continue
            if _POSE_RE.match(nxt) or nxt in vocab.variant_words:
                tokens.pop()
                continue
            if _TRAIL_RE.match(tok) and tok.isdigit() is False and tok in ("a", "b", "c", "d"):
                saw_variant = True
                tokens.pop()
                continue
            if tok.isdigit():  # bare trailing number: pose-ish
                saw_variant = True
                tokens.pop()
                continue
            tokens.pop()
            continue
        if _POSE_RE.match(tok):
            saw_variant = True
            tokens.pop()
            continue
        if _PART_N_RE.match(tok):
            saw_part = True
            tokens.pop()
            continue
        if tok in vocab.part_words:
            saw_part = True
            tokens.pop()
            continue
        if tok in vocab.variant_words:
            saw_variant = True
            tokens.pop()
            continue
        if tok in vocab.marker_words or _SCALE_RE.match(tok):
            markers.add(tok)
            tokens.pop()
            continue
        break
    core = "_".join(tokens) if tokens else stem.replace(" ", "_")
    role = "part" if saw_part else ("variant" if saw_variant else "model")
    return NormalizedName(core=core, role=role, markers=markers)


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


def group_folder(stl_records: list[FileRecord], vocab: Vocab, cfg: Config) -> list[ModelGroup]:
    if not stl_records:
        return []
    normalized = [(r, normalize_stem(Path(r.rel_path).name, vocab)) for r in stl_records]
    buckets: dict[str, list[tuple[FileRecord, NormalizedName]]] = {}
    for r, n in normalized:
        buckets.setdefault(n.core, []).append((r, n))

    cores = sorted(buckets)
    merged: list[list[str]] = []
    for core in cores:
        placed = False
        for cluster in merged:
            if any(fuzz.token_set_ratio(core, c) >= cfg.group_similarity for c in cluster):
                cluster.append(core)
                placed = True
                break
        if not placed:
            merged.append([core])

    groups: list[ModelGroup] = []
    for cluster in merged:
        pairs = [(a, b) for a, b in combinations(cluster, 2)]
        conf = (
            (sum(fuzz.token_set_ratio(a, b) for a, b in pairs) / len(pairs) / 100) if pairs else 1.0
        )
        members = [GroupMember(r, n.role) for c in cluster for (r, n) in buckets[c]]
        members.sort(key=lambda m: m.record.rel_path)
        title = max(cluster, key=len).replace("_", " ").title()
        groups.append(ModelGroup(members, title, _assembly(members), conf))

    if any(g.confidence < cfg.group_confidence_min for g in groups):
        all_members = [GroupMember(r, n.role) for r, n in normalized]
        all_members.sort(key=lambda m: m.record.rel_path)
        folder = Path(stl_records[0].rel_path).parent.name or "Ungrouped"
        return [
            ModelGroup(
                all_members,
                folder.replace("_", " ").title(),
                "needs-review",
                min(g.confidence for g in groups),
            )
        ]
    return sorted(groups, key=lambda g: g.title)
