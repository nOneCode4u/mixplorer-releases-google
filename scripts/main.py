"""
APK Update Pipeline — Orchestrator

Flow
----
1. Check STATE.md — exit immediately if Paused.
2. Load config, version cache, and manual overrides.
3. Discover app folders on Google Drive.
4. For each app:
   a. Download all APK variants.
   b. Extract version (multi-method + cross-verify).
   c. Rename to standard format.
   d. Compare with released_versions.json.
   e. If new version: create GitHub Release + upload + verify.
5. Save updated version cache.
6. Update STATE.md.
"""
import json
import os
import re
import shutil
import sys
import tempfile
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Path setup ────────────────────────────────────────────────────────────────
_SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPTS_DIR))

from logger import get_logger
from state_manager import read_state, write_state
from drive_client import DriveClient, DriveError
from apk_extractor import extract_apk_info, APKInfo
from apk_renamer import (
    load_rename_map, save_rename_map,
    auto_map_folder_name, get_display_name,
    finalize_filenames,
)
from release_manager import ReleaseManager, GitHubError
from notifier import Notifier

log = get_logger("main")

# ── Environment ───────────────────────────────────────────────────────────────
GDRIVE_API_KEY   = os.environ["GDRIVE_API_KEY"]
GH_TOKEN         = os.environ["GH_TOKEN"]
GH_REPO          = os.environ["GH_REPO"]
ROOT_FOLDER_ID   = os.environ.get("GDRIVE_ROOT_FOLDER_ID", "1BfeK39boriHy-9q76eXLLqbCwfV17-Gv")
FORCE_ALL        = os.environ.get("FORCE_ALL",  "false").lower() == "true"
DEBUG_MODE       = os.environ.get("DEBUG_MODE", "false").lower() == "true"

# ── Paths ─────────────────────────────────────────────────────────────────────
VERSIONS_FILE        = Path("data/released_versions.json")
MANUAL_VERSIONS_FILE = Path("MANUAL_VERSIONS.md")
DESCRIPTIONS_FILE    = Path("config/descriptions.json")
RENAME_MAP_FILE      = Path("config/rename_map.json")


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_json(path: Path, default):
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def load_manual_overrides() -> dict[str, dict]:
    """
    Parse MANUAL_VERSIONS.md for completed override entries.

    Table format:
        | filename.apk | versionName | versionCode | arch | AppName |

    Skips rows that still contain 'FILL_ME', header rows, and separator rows.
    """
    overrides: dict[str, dict] = {}
    if not MANUAL_VERSIONS_FILE.exists():
        return overrides

    for line in MANUAL_VERSIONS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("|") or "|---|" in line:
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 4:
            continue
        filename, vn, vc = parts[0], parts[1], parts[2]
        arch = parts[3] if len(parts) > 3 else "java"
        if "FILL_ME" in (vn, vc) or not vn or not vc:
            continue
        if "Filename" in filename:   # Header row
            continue
        overrides[filename] = {
            "version_name": vn,
            "version_code": vc,
            "arch": arch,
        }
    log.info(f"Loaded {len(overrides)} manual override(s)")
    return overrides


def append_pending_overrides(entries: list[dict]) -> None:
    """
    Add new 'FILL_ME' rows to the Pending section of MANUAL_VERSIONS.md.
    """
    if not entries:
        return

    if not MANUAL_VERSIONS_FILE.exists():
        MANUAL_VERSIONS_FILE.write_text(
            "# Manual Version Overrides\n\n"
            "> Fill in `FILL_ME` cells, then set `STATE.md` → `Resumed`.\n\n"
            "## Pending (Fill these in)\n\n"
            "| Filename | versionName | versionCode | arch | App |\n"
            "|---|---|---|---|---|\n",
            encoding="utf-8",
        )

    content  = MANUAL_VERSIONS_FILE.read_text(encoding="utf-8")
    new_rows = [
        f"| {e['filename']} | FILL_ME | FILL_ME | {e.get('arch', 'java')} | {e['app_name']} |"
        for e in entries
    ]

    # Insert after the pending table separator
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if "## Pending" in line:
            for j in range(i, min(i + 6, len(lines))):
                if "|---|" in lines[j]:
                    lines = lines[: j + 1] + new_rows + lines[j + 1 :]
                    MANUAL_VERSIONS_FILE.write_text("\n".join(lines), encoding="utf-8")
                    return
    # Section not found → append
    MANUAL_VERSIONS_FILE.write_text(
        content + "\n" + "\n".join(new_rows) + "\n",
        encoding="utf-8",
    )


def build_release_body(
    app_name: str,
    version_name: str,
    descriptions: dict,
    asset_names: list[str],
) -> str:
    info        = descriptions.get(app_name, {})
    display     = info.get("display_name", get_display_name(app_name))
    description = info.get("description", "Android application by H. Parsa.")
    icon        = info.get("icon", "📦")
    category    = info.get("category", "Android App")

    def arch_label(fname: str) -> str:
        """Human-readable architecture label from filename."""
        fl = fname.lower()
        if "-universal" in fl:
            return "Universal · all architectures"
        if "-arm64" in fl:
            return "ARM 64-bit · arm64-v8a ⭐ Recommended"
        if "-arm" in fl:
            return "ARM 32-bit · armeabi-v7a"
        if "-x64" in fl:
            return "x86 64-bit · x86_64"
        if "-x86" in fl:
            return "x86 32-bit"
        return "Universal · Pure-Java (all devices)"

    def install_note(fname: str) -> str:
        fl = fname.lower()
        if "-arm64" in fl:
            return "Best for most modern Android phones (2016+)"
        if "-arm" in fl:
            return "For older 32-bit ARM phones"
        if "-x64" in fl:
            return "For 64-bit x86 devices and modern emulators"
        if "-x86" in fl:
            return "For older 32-bit x86 devices and emulators"
        if "-universal" in fl:
            return "Works on any device; largest file size"
        return "Works on all devices"

    rows = "\n".join(
        f"| [`{f}`]"
        f"(https://github.com/nOneCode4u/mixplorer-releases-google/releases/download/{app_name}-v{version_name}/{f})"
        f" | {arch_label(f)} | {install_note(f)} |"
        for f in sorted(asset_names)
    )

    return f"""\
## {icon} {display}

{description}

---

### Download

| File | Architecture | Notes |
|------|-------------|-------|
{rows}

> **Not sure which to choose?**  
> Download **`-arm64`** — it works on virtually all Android phones made since 2016.  
> If `-arm64` is not listed, download the variant with no suffix (Universal / Pure-Java).

---

*Category: {category} · Source: Official Google Drive · Mirrored automatically.*
"""


# ── Per-app processor ─────────────────────────────────────────────────────────

def process_app(
    *,
    drive:             DriveClient,
    rm:                ReleaseManager,
    notifier:          Notifier,
    folder_info:       dict,
    app_name:          str,
    released_versions: dict,
    descriptions:      dict,
    manual_overrides:  dict,
    work_dir:          Path,
) -> tuple[bool, Optional[dict]]:
    """
    Download, extract, rename, and release one app.

    Returns
    -------
    (success, release_info_dict | None)
      success=True, release_info=None  → already up-to-date
      success=True, release_info=dict  → new release created
      success=False                    → error (state already set to Paused)
    """
    folder_id = folder_info["id"]
    log.info(f"{'─' * 50}")
    log.info(f"App: {app_name}  (Drive folder: {folder_info['name']})")

    # ── List APKs ────────────────────────────────────────────────────────
    apk_metas = drive.list_apks(folder_id)
    if not apk_metas:
        log.warning(f"No APKs found in folder for {app_name} — skipping.")
        return True, None

    log.info(f"Found {len(apk_metas)} APK(s): {[m['name'] for m in apk_metas]}")

    app_dir = work_dir / app_name
    app_dir.mkdir(parents=True, exist_ok=True)

    # ── Download ─────────────────────────────────────────────────────────
    downloaded: list[tuple[Path, dict]] = []
    failed_downloads: list[str] = []

    for meta in apk_metas:
        dest = app_dir / meta["name"]
        ok   = drive.download_file(meta["id"], dest, expected_md5=meta.get("md5Checksum"))
        if ok:
            downloaded.append((dest, meta))
        else:
            failed_downloads.append(meta["name"])

    if failed_downloads:
        notifier.download_failure(failed_downloads, app_name)
        write_state("Paused", "Download failure", f"{app_name}: {failed_downloads}")
        return False, None

    # ── Extract versions ─────────────────────────────────────────────────
    apk_infos: list[tuple[Path, APKInfo]] = []
    failed_extractions: list[str] = []

    for path, meta in downloaded:
        override = manual_overrides.get(meta["name"])
        if override:
            log.info(f"  Using manual override for {meta['name']}")
            info = APKInfo(
                version_name  = override["version_name"],
                version_code  = override["version_code"],
                package_name  = "manual-override",
                arch          = override.get("arch", "java"),
                source_methods= ["manual"],
                confidence    = "manual",
            )
            apk_infos.append((path, info))
            continue

        try:
            info = extract_apk_info(path)
        except Exception as exc:
            log.error(f"  Extraction exception for {meta['name']}: {exc}")
            info = None

        if info is None:
            failed_extractions.append(meta["name"])
        else:
            apk_infos.append((path, info))

    if failed_extractions:
        append_pending_overrides(
            [{"filename": f, "app_name": app_name, "arch": "unknown"}
             for f in failed_extractions]
        )
        notifier.extraction_failure(failed_extractions, app_name)
        write_state("Paused", "Extraction failure", f"{app_name}: {failed_extractions}")
        return False, None

    if not apk_infos:
        log.error(f"No APKInfo produced for {app_name}")
        return False, None

    # ── Sanity-check: all APKs should share the same versionName ─────────
    version_counts = Counter(i.version_name for _, i in apk_infos)
    primary_version, primary_count = version_counts.most_common(1)[0]
    if len(version_counts) > 1:
        log.warning(
            f"Mixed versions in {app_name}: {dict(version_counts)}. "
            f"Using majority: {primary_version}"
        )
        apk_infos = [(p, i) for p, i in apk_infos if i.version_name == primary_version]

    version_name = primary_version

    # ── Version already released? ─────────────────────────────────────────
    cached = released_versions.get(app_name, {})
    if not FORCE_ALL and cached.get("version_name") == version_name:
        log.info(f"  {app_name} v{version_name} already released — nothing to do.")
        return True, None

    log.info(f"  New version detected: {app_name} v{version_name}")

    # ── Rename APKs ───────────────────────────────────────────────────────
    renamed_pairs = finalize_filenames(app_name, apk_infos)

    final_files: list[Path] = []
    for src, new_name in renamed_pairs:
        dst = app_dir / new_name
        shutil.copy2(src, dst)
        final_files.append(dst)
        log.info(f"  Renamed: {src.name}  →  {new_name}")

    # ── Create / reuse GitHub release ────────────────────────────────────
    tag          = f"{app_name}-v{version_name}"
    release_name = f"{get_display_name(app_name)} v{version_name}"
    release_body = build_release_body(
        app_name, version_name, descriptions,
        [f.name for f in final_files],
    )

    existing = rm.get_release_by_tag(tag)
    if existing and not FORCE_ALL:
        log.info(f"  Release {tag} already exists on GitHub — skipping.")
        return True, None

    if existing and FORCE_ALL:
        release_id = existing["id"]
        log.info(f"  FORCE_ALL: reusing existing release id={release_id}")
    else:
        release    = rm.create_release(tag, release_name, release_body)
        release_id = release["id"]

    # ── Upload assets ─────────────────────────────────────────────────────
    upload_errors: list[str] = []
    for file_path in final_files:
        try:
            rm.upload_asset(release_id, file_path)
        except Exception as exc:
            log.error(f"  Upload failed for {file_path.name}: {exc}")
            upload_errors.append(file_path.name)

    # ── Post-upload verification ──────────────────────────────────────────
    expected = [f.name for f in final_files]
    if not rm.verify_release(release_id, expected):
        missing = [n for n in expected if n not in set()]
        notifier.upload_failure(tag, missing)
        return False, None

    return True, {
        "version_name": version_name,
        "version_code": apk_infos[0][1].version_code,
        "release_tag":  tag,
        "release_id":   release_id,
        "assets":       expected,
        "updated_at":   datetime.now(timezone.utc).isoformat(),
    }


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    log.info("=" * 60)
    log.info("APK Update Pipeline — Start")
    log.info(f"  Repository : {GH_REPO}")
    log.info(f"  Force all  : {FORCE_ALL}")
    log.info(f"  Debug      : {DEBUG_MODE}")
    log.info("=" * 60)

    # ── State check ───────────────────────────────────────────────────────
    state = read_state()
    log.info(f"Workflow state: {state}")
    if state == "Paused":
        log.info("State is Paused — exiting without processing.")
        sys.exit(0)

    # ── Initialise clients ────────────────────────────────────────────────
    drive    = DriveClient(GDRIVE_API_KEY)
    rm       = ReleaseManager(GH_TOKEN, GH_REPO)
    notifier = Notifier(rm)

    # ── Load config ───────────────────────────────────────────────────────
    released_versions = load_json(VERSIONS_FILE, {})
    descriptions      = load_json(DESCRIPTIONS_FILE, {})
    manual_overrides  = load_manual_overrides()
    rename_map        = load_rename_map()

    log.info(f"Previously released apps: {list(released_versions.keys())}")

    # ── Discover Drive folders ────────────────────────────────────────────
    try:
        subfolders = drive.list_subfolders(ROOT_FOLDER_ID)
    except DriveError as exc:
        log.error(f"Cannot list Drive root: {exc}")
        write_state("Error", "Drive API failure", str(exc))
        notifier.critical_error("Listing Drive root folder", str(exc))
        sys.exit(1)

    log.info(f"Drive app folders: {[f['name'] for f in subfolders]}")

    # Map folder names → app names (auto-discover new apps)
    app_folders: list[tuple[dict, str]] = []
    for folder in subfolders:
        fname = folder["name"]
        if fname in rename_map:
            app_name = rename_map[fname]
        else:
            app_name = auto_map_folder_name(fname)
            log.info(f"Auto-mapped new folder: {fname!r} → {app_name!r}")
            rename_map[fname] = app_name
            save_rename_map(rename_map)
            notifier.new_app_discovered(fname, app_name)
        app_folders.append((folder, app_name))

    # ── Process each app ──────────────────────────────────────────────────
    results: dict[str, str] = {}
    overall_success = True

    with tempfile.TemporaryDirectory(prefix="apk_update_") as tmp:
        work_dir = Path(tmp)

        for folder_info, app_name in app_folders:
            try:
                ok, release_info = process_app(
                    drive             = drive,
                    rm                = rm,
                    notifier          = notifier,
                    folder_info       = folder_info,
                    app_name          = app_name,
                    released_versions = released_versions,
                    descriptions      = descriptions,
                    manual_overrides  = manual_overrides,
                    work_dir          = work_dir,
                )
            except (DriveError, GitHubError) as exc:
                log.error(f"API error for {app_name}: {exc}")
                write_state("Error", f"API error in {app_name}", str(exc))
                notifier.critical_error(app_name, traceback.format_exc())
                results[app_name] = "api_error"
                overall_success = False
                break
            except Exception as exc:
                log.exception(f"Unexpected error for {app_name}: {exc}")
                write_state("Error", f"Unexpected error in {app_name}", str(exc))
                notifier.critical_error(app_name, traceback.format_exc())
                results[app_name] = "exception"
                overall_success = False
                break

            if ok and release_info:
                released_versions[app_name] = release_info
                results[app_name] = "released"
                log.info(f"✓ Released: {app_name} v{release_info['version_name']}")
            elif ok:
                results[app_name] = "no_update"
                log.info(f"○ No update: {app_name}")
            else:
                results[app_name] = "failed"
                overall_success = False
                log.error(f"✗ Failed: {app_name}")
                break    # State already set to Paused inside process_app

    # ── Persist results ───────────────────────────────────────────────────
    save_json(VERSIONS_FILE, released_versions)

    # ── Summary ───────────────────────────────────────────────────────────
    released_n  = sum(1 for v in results.values() if v == "released")
    skipped_n   = sum(1 for v in results.values() if v == "no_update")
    failed_n    = sum(1 for v in results.values() if v not in ("released", "no_update"))
    summary     = f"Released={released_n}  Skipped={skipped_n}  Failed={failed_n}"

    log.info("=" * 60)
    log.info(f"Pipeline complete — {summary}")
    log.info(f"Results: {results}")
    log.info("=" * 60)

    if overall_success:
        if state == "Resumed":
            log.info("State was Resumed → resetting to Running")
        write_state("Running", "Success", summary)
    # (Failure state was already written inside process_app)

    sys.exit(0 if overall_success else 1)


if __name__ == "__main__":
    main()
