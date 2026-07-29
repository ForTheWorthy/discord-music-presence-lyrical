# AGENTS.md

## Cursor Cloud specific instructions

### What this repository is

This is the public **documentation, assets, and release-management** repository for
the *Music Presence* desktop app (`ungive/discord-music-presence`). The actual
C++/Qt application source code is **not** in this repository, so there is no app to
compile or run here. "Development" means editing the docs/assets/changelog and
running the maintenance tooling in `.github/scripts/`.

### Tooling and dependencies

- The only runnable code is the scripts in `.github/scripts/` (bash + Python 3).
- The Python scripts use the **standard library only** — there is nothing to
  `pip install`. Requirements are just `python3`, `git`, `sed`, `bash`, and `gh`
  (GitHub CLI), all preinstalled on the VM.
- There is no lint config, no automated test suite, and no build system in this repo.

### Running the scripts (see `.github/scripts/README.md` for details)

- `.github/scripts/generate-release-changelog X.Y.Z` — fully self-contained; reads
  `CHANGELOG.md`, reformats the matching `## X.Y.Z` section via `fix-changelog.py`,
  and writes `.github/scripts/out/changelog.md`. `out/` is gitignored. This is the
  easiest way to verify the tooling works end-to-end.
- `.github/scripts/update-download-buttons.py` and
  `.github/scripts/update-latest-changelog` both call
  `git describe --tags` and require an existing `vX.Y.Z` tag. **The cloud clone has
  no tags** (`git ls-remote --tags origin` is empty), so these scripts fail with
  "failed to get latest git tag" / "cannot describe anything" until a tag exists.
  `update-latest-changelog` additionally needs an authenticated `gh` and a matching
  GitHub release, so it cannot be fully exercised in this environment.
