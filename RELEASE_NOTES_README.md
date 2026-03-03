# Release notes and multi-version upgrades

## For you (developer): RELEASE_NOTES.txt

### Format

Use **version markers** so one file can hold notes for several releases:

```text
## 1.8.14
- Fixed font command crash in EC/GC interactive menu
- Fixed mathtext.fontset not restoring on undo

## 1.8.15
- Improved error messages

## 1.8.20
- New feature X
- Performance improvements
```

**Rules:**

1. **Marker:** `##` followed by a space and the version number (e.g. `## 1.8.14`).
2. **One block per version.** Order blocks from oldest to newest.
3. **When you run `batplot --dev-upgrade`**, the new version is read from the latest `## VERSION` in this file (no prompt).
   - Only the block for **that** version is used for the “What’s new” message and for `version_check.py`.
   - **All** blocks are merged into `CHANGELOG.md` (so you can backfill 1.8.14, 1.8.15, 1.8.20 in one go).
4. Lines starting with `#` are comments and ignored.

### Workflow

1. Edit `RELEASE_NOTES.txt`: add a block for the version you’re about to release (and optionally for older versions you never wrote notes for).
2. Run `batplot --dev-upgrade`. The latest `## VERSION` from the file is applied automatically (no typing).
3. The script uses the matching block for the update message and merges all blocks into `CHANGELOG.md`.
4. After a successful upload, `RELEASE_NOTES.txt` is cleared back to the template.

### Catching up several versions

If you’re releasing 1.8.20 and never wrote notes for 1.8.14–1.8.19, add one block per version:

```text
## 1.8.14
- Fix A

## 1.8.15
- Fix B

## 1.8.20
- Fix C
```

Then run `batplot --dev-upgrade` (1.8.20 is picked automatically). Only the 1.8.20 block is used for the “What’s new” box; all three blocks are added to `CHANGELOG.md` so users see full history when they press `v`.

---

## For users: “v” for full release notes

When a user has an older version and runs `batplot`:

1. They see the usual update box (current → latest, “What’s new”, `pip install --upgrade batplot`).
2. If they’re **more than one version behind**, the box says:  
   **“(X versions behind — press 'v' for full release notes)”**.
3. Under the box it says: **“Press 'v' for full release notes, or Enter to continue”**.
4. If they press **v**, the full changelog is read from the file shipped with the package (`batplot/data/CHANGELOG.md`) and printed—no network, no GitHub.
5. If they press **Enter**, batplot continues as usual.

So: one version behind → same box + option to press `v`. Several versions behind → box + “X versions behind” + same `v` / Enter choice. In all cases, `v` shows the full changelog that was included when the package was built.

---

## How the changelog reaches users

The “v” command reads from the package file (no network):

(Changelog is read from the package file batplot/data/CHANGELOG.md — no URL.)

Nothing is fetched from GitHub or any other URL.
