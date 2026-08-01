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
