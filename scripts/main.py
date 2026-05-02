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
import urllib.parse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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
from changelog_fetcher import fetch_xda_changelog

log = get_logger("main")

# ── Environment ───────────────────────────────────────────────────────────────
GDRIVE_API_KEY  = os.environ["GDRIVE_API_KEY"]
GH_TOKEN        = os.environ["GH_TOKEN"]
GH_REPO         = os.environ["GH_REPO"]           # e.g. "nOneCode4u/mixplorer-google-drive"
ROOT_FOLDER_ID  = os.environ.get("GDRIVE_ROOT_FOLDER_ID", "1BfeK39boriHy-9q76eXLLqbCwfV17-Gv")
FORCE_ALL       = os.environ.get("FORCE_ALL",  "false").lower() == "true"
DEBUG_MODE      = os.environ.get("DEBUG_MODE", "false").lower() == "true"

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
    """Parse MANUAL_VERSIONS.md for completed override entries."""
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
        if "Filename" in filename:
            continue
        overrides[filename] = {
            "version_name": vn,
            "version_code": vc,
            "arch": arch,
        }
    log.info(f"Loaded {len(overrides)} manual override(s)")
    return overrides


def append_pending_overrides(entries: list[dict]) -> None:
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
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if "## Pending" in line:
            for j in range(i, min(i + 6, len(lines))):
                if "|---|" in lines[j]:
                    lines = lines[: j + 1] + new_rows + lines[j + 1:]
                    MANUAL_VERSIONS_FILE.write_text("\n".join(lines), encoding="utf-8")
                    return
    MANUAL_VERSIONS_FILE.write_text(
        content + "\n" + "\n".join(new_rows) + "\n", encoding="utf-8"
    )


def _generate_obtainium_deep_link(app_name: str, display_name: str) -> str:
    """
    Generate a fully pre-configured Obtainium deep link for one app.
    Uses the corrected tag prefix format: {app_name}_v
    """
    config = {
        "id": f"github.com/{GH_REPO}/{app_name.lower().replace('_', '-')}",
        "url": f"https://github.com/{GH_REPO}",
        "author": "H. Parsa",
        "name": display_name,
        "preferredApkIndex": 0,
        "additionalSettings": json.dumps({
            "includePrereleases": False,
            "fallbackToOlderReleases": True,
            "filterReleaseTitlesByRegEx": f"{app_name}_v",
            "filterReleaseNotesByRegEx": "",
            "verifyLatestTag": False,
            "dontSortReleasesList": True,
            "autoApkFilterByArch": True,
            "apkFilterRegEx": "",
            "invertAPKFilter": False,
        }),
    }
    encoded = urllib.parse.quote(
        json.dumps(config, separators=(",", ":")), safe=""
    )
    return f"https://apps.obtainium.imranr.dev/redirect?r=obtainium://app/{encoded}"


def build_release_body(
    app_name: str,
    version_name: str,
    descriptions: dict,
    changelog: str,
) -> str:
    """
    Build the release description body.

    Contains:
      - App name heading (no version — version is already in the release title)
      - Obtainium one-tap badge
      - Changelog section
    """
    info        = descriptions.get(app_name, {})
    display     = info.get("display_name", get_display_name(app_name))
    icon        = info.get("icon", "📦")
    obtainium_url = _generate_obtainium_deep_link(app_name, display)

    return f"""\
## {icon} {display}

[![Get on Obtainium](https://img.shields.io/badge/Obtainium-Get%20App-7040D4?style=flat-square)]({obtainium_url})

---

### What's New

{changelog}

---

*Mirrored automatically from the developer's official Google Drive.*
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
      success=True,  release_info=None  → already up-to-date
      success=True,  release_info=dict  → new release created
      success=False                     → error (state set to Paused)
    """
    folder_id = folder_info["id"]
    log.info(f"{'─' * 50}")
    log.info(f"App: {app_name}  (Drive folder: {folder_info['name']})")

    apk_metas = drive.list_apks(folder_id)
    if not apk_metas:
        log.warning(f"No APKs found for {app_name} — skipping.")
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
            log.info(f"  Manual override applied for {meta['name']}")
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

    # ── Validate: no double-version in any filename ───────────────────────
    for f in final_files:
        # Filename pattern must be: AppName_vX.Y.Z_BCODE[-arch].apk
        # Detect if vX.Y.Z appears twice in the name
        version_occurrences = re.findall(r'_v\d+[\.\d]*', f.name)
        if len(version_occurrences) > 1:
            log.error(
                f"  DOUBLE VERSION DETECTED in filename: {f.name}  "
                f"occurrences={version_occurrences}. "
                "Check rename_map.json — app_name likely contains a version suffix."
            )
            write_state("Paused", "Filename validation failure", f.name)
            notifier.critical_error(
                "Double version in filename",
                f"Filename '{f.name}' contains the version twice. "
                "Update config/rename_map.json to map the Drive folder name "
                "to a clean app name without version suffix."
            )
            return False, None

    # ── Fetch changelog ───────────────────────────────────────────────────
    # Only MiXplorer has a public XDA thread; add-ons use the same thread
    changelog = fetch_xda_changelog(version_name)

    # ── Release title format: "MiX Archive v3.20" ─────────────────────────
    # NOTE: display_name already has spaces (e.g. "MiX Archive")
    # version_name is the clean version (e.g. "3.20")
    # release_name = "{DisplayName} v{version}" — no duplication
    display = descriptions.get(app_name, {}).get("display_name", get_display_name(app_name))
    release_name = f"{display} v{version_name}"

    # ── Tag format: AppName_vVersion (underscore, no dash before v) ───────
    tag = f"{app_name}_v{version_name}"

    release_body = build_release_body(
        app_name, version_name, descriptions, changelog
    )

    # ── Create release ────────────────────────────────────────────────────
    existing = rm.get_release_by_tag(tag)
    if existing and not FORCE_ALL:
        log.info(f"  Release {tag} already exists — skipping.")
        return True, None

    if existing and FORCE_ALL:
        release_id = existing["id"]
        log.info(f"  FORCE_ALL: reusing existing release id={release_id}")
    else:
        release    = rm.create_release(tag, release_name, release_body)
        release_id = release["id"]

    # ── Upload assets ─────────────────────────────────────────────────────
    for file_path in final_files:
        try:
            rm.upload_asset(release_id, file_path)
        except Exception as exc:
            log.error(f"  Upload failed for {file_path.name}: {exc}")

    # ── Post-upload verification ──────────────────────────────────────────
    expected = [f.name for f in final_files]
    if not rm.verify_release(release_id, expected):
        notifier.upload_failure(tag, expected)
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

    log.info(f"Previously released: {list(released_versions.keys())}")

    # ── Discover Drive folders ────────────────────────────────────────────
    try:
        subfolders = drive.list_subfolders(ROOT_FOLDER_ID)
    except DriveError as exc:
        log.error(f"Cannot list Drive root: {exc}")
        write_state("Error", "Drive API failure", str(exc))
        notifier.critical_error("Listing Drive root folder", str(exc))
        sys.exit(1)

    log.info(f"Drive folders found: {[f['name'] for f in subfolders]}")

    # ── Map folder names → app names ──────────────────────────────────────
    app_folders: list[tuple[dict, str]] = []
    for folder in subfolders:
        fname = folder["name"]
        if fname in rename_map:
            app_name = rename_map[fname]
        else:
            app_name = auto_map_folder_name(fname)
            log.info(f"Auto-mapped: {fname!r} → {app_name!r}")
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
                overall_success   = False
                break
            except Exception as exc:
                log.exception(f"Unexpected error for {app_name}: {exc}")
                write_state("Error", f"Unexpected error in {app_name}", str(exc))
                notifier.critical_error(app_name, traceback.format_exc())
                results[app_name] = "exception"
                overall_success   = False
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
                overall_success   = False
                log.error(f"✗ Failed: {app_name}")
                break

    # ── Persist results ───────────────────────────────────────────────────
    save_json(VERSIONS_FILE, released_versions)

    # ── Summary ───────────────────────────────────────────────────────────
    released_n = sum(1 for v in results.values() if v == "released")
    skipped_n  = sum(1 for v in results.values() if v == "no_update")
    failed_n   = sum(1 for v in results.values() if v not in ("released", "no_update"))
    summary    = f"Released={released_n}  Skipped={skipped_n}  Failed={failed_n}"

    log.info("=" * 60)
    log.info(f"Pipeline complete — {summary}")
    log.info(f"Results: {results}")
    log.info("=" * 60)

    if overall_success:
        write_state("Running", "Success", summary)

    sys.exit(0 if overall_success else 1)


if __name__ == "__main__":
    main()
