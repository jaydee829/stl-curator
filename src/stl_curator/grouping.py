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
