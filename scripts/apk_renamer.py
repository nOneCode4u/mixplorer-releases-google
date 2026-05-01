"""
Rename APKs to the standardised format:

    {AppName}_v{versionName}_B{versionCode}[-{arch_suffix}].apk

Arch suffix rules (matches developer's convention exactly):
    java      → (no suffix)   — pure Java, works on all architectures
    arm       → -arm
    arm64     → -arm64
    x86       → -x86
    x64       → -x64
    universal → -universal    — fat APK containing multiple native-lib sets
"""
import json
import re
from pathlib import Path
from typing import Optional

from apk_extractor import APKInfo
from logger import get_logger

log = get_logger(__name__)

RENAME_MAP_PATH = Path("config/rename_map.json")

_ARCH_SUFFIX: dict[str, str] = {
    "java":      "",
    "arm":       "-arm",
    "arm64":     "-arm64",
    "x86":       "-x86",
    "x64":       "-x64",
    "universal": "-universal",
}


def load_rename_map() -> dict[str, str]:
    with open(RENAME_MAP_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def save_rename_map(mapping: dict[str, str]) -> None:
    with open(RENAME_MAP_PATH, "w", encoding="utf-8") as fh:
        json.dump(mapping, fh, indent=2, ensure_ascii=False)
    log.debug(f"Saved rename map ({len(mapping)} entries)")


def auto_map_folder_name(folder_name: str) -> str:
    """
    Convert an unknown Drive folder name to a standardised app name.

    Rules:
      'MiXplorer'   →  'MiXplorer'   (special case: no underscore)
      'MiXFoo'      →  'MiX_Foo'
      'MiXFooBar'   →  'MiX_FooBar'
      anything else →  spaces → underscores (last-resort fallback)
    """
    if folder_name == "MiXplorer":
        return "MiXplorer"

    m = re.match(r"^(MiX)([A-Z].*)$", folder_name)
    if m:
        return f"{m.group(1)}_{m.group(2)}"

    # Last-resort: sanitise to filesystem-safe name
    return re.sub(r"\s+", "_", folder_name)


def get_display_name(app_name: str) -> str:
    """'MiX_Archive' → 'MiX Archive'"""
    return app_name.replace("_", " ")


def build_filename(app_name: str, info: APKInfo) -> str:
    """
    Build the final APK filename for a single APK.

    The caller is responsible for passing an APKInfo whose .arch has already
    been finalized (e.g. 'java' for a universal pure-Java APK, 'arm64' for
    an architecture-specific one, etc.).
    """
    suffix = _ARCH_SUFFIX.get(info.arch, f"-{info.arch}")
    return f"{app_name}_v{info.version_name}_B{info.version_code}{suffix}.apk"


def finalize_filenames(
    app_name: str,
    apk_infos: list[tuple[Path, APKInfo]],
) -> list[tuple[Path, str]]:
    """
    Determine the final filename for every APK variant of an app.

    Sorting by versionCode (ascending) is used only for logging consistency.
    The naming logic is driven purely by the detected arch type.
    """
    sorted_pairs = sorted(apk_infos, key=lambda x: _safe_int(x[1].version_code))

    results: list[tuple[Path, str]] = []
    for path, info in sorted_pairs:
        filename = build_filename(app_name, info)
        results.append((path, filename))
        log.debug(f"  {path.name}  →  {filename}")

    return results


def _safe_int(s: str, default: int = 0) -> int:
    try:
        return int(s)
    except (ValueError, TypeError):
        return default
