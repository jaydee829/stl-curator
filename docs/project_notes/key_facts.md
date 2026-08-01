# Key Project Facts

This file tracks important project configuration, constants, and environment details.

## Project Overview
- **Project Name**: STL Curator
- **Description**: Graph+tag curator for a multi-hundred-GB local STL library — flat storage,
  generated Obsidian vault (markdown + YAML frontmatter), rebuildable SQLite cache.
- **Design doc**: `STL_CURATOR_SEED.md` (settled decisions, roadmap, open questions)

## Local Development
- **OS / Runtime**: Windows 11, Python 3.11+ (system Python 3.14.3; uv manages project interpreter)
- **Tooling (verified installed 2026-08-01)**: git 2.44, gh CLI 2.93, uv 0.11.17
- **Package/env management**: `uv` — `uv sync` for deps, `uv run <cmd>` for everything
- **Lint/format**: `ruff` as a uv dev dependency (`uv run ruff check`, `uv run ruff format`) — not installed globally
- **Vault app**: Obsidian (reads the generated markdown vault; Dataview/Bases for queries)
- **Repo split (ADR-002)**: code repo = public GitHub; `vault/` = separate private repo, gitignored in the code repo
- **Primary Workflow**: `typer` CLI ingest pipeline run against the local STL store (planned)
- **Sample data**: `example_stls/` — staging area for test models (being populated from cloud)
- **Setup**: TBD once the package skeleton exists (`uv sync` will be the entry point)

## Technology Stack (planned)
- **Storage**: local disk (STLs/zips/thumbnails, never in git); SQLite as rebuildable cache
- **Vault**: Obsidian markdown + YAML frontmatter, private GitHub repo (text only)
- **Key Libraries**: `trimesh` + `pyrender` (mesh facts, offscreen renders), `httpx` (MMF API),
  `python-frontmatter`/`pyyaml`, `rapidfuzz`, `typer`
- **Testing**: `pytest` (parametrized tests per global preference)
- **LLM tagging (v1.5)**: provider-abstracted, vision-capable (Claude or Gemini)

## External Services
- **MMF API**: OAuth2; spec at github.com/MyMiniFactory/api-documentation
  (`myminifactory-api.yaml`). No "my purchases" endpoint — ownership bridged via collections.
- **Backup**: `rclone sync` to existing Google Drive / OneDrive with
  `--backup-dir` trash convention. No GCP, zero new cloud spend.

## Conventions
- **Thumbnails**: content-addressed by STL hash — `thumbs/ab/abcd1234….webp`
- **Model notes**: `models/<creator>--<model-name>.md`; entity notes in
  `creators/`, `campaigns/`, `projects/`
- **Frontmatter schema v1**: see `STL_CURATOR_SEED.md` § "Vault Design"

## Usage Tips
- Organize facts by category; prefer bullet lists over tables for easy editing.
- Include both production and development details, and add URLs for navigation.
- Prefer documented facts here over assumptions when looking up config.

## SECURITY — What NOT to Store

This file is committed to version control. **Never** put secrets here:

- ❌ Passwords, API keys, tokens, private keys, connection strings with embedded credentials
- ❌ `.env` file contents, OAuth client secrets (including MMF API client secrets), signing keys
- ❌ Anything you would not paste into a public PR

Instead, store:

- ✅ The **name/location** of a secret and how to obtain it
  (e.g., "MMF OAuth client secret lives in `.env` as `MMF_CLIENT_SECRET`; create clients
  in MMF account settings").
- ✅ Non-secret config: ports, hostnames, public URLs, remote names.

If a secret ever lands in this file, treat it as compromised: rotate it and scrub history.
