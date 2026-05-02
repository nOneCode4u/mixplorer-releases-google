"""
Changelog extractor for MiXplorer APKs.

Strategy (in priority order):
  1. Read directly from the APK zip file (assets/ and res/raw/).
  2. Dump string resources via aapt and search for changelog keys.
  3. Fall back to a polite placeholder.

The developer includes changelogs inside the APK (visible in app Settings).
They are most likely stored in assets/ as plain text files.
"""
import os
import re
import subprocess
import zipfile
from pathlib import Path
from typing import Optional

from logger import get_logger

log = get_logger(__name__)

AAPT_PATH: str = os.environ.get("AAPT_PATH", "aapt")

_XDA_URL = (
    "https://xdaforums.com/t/"
    "app-2-2-mixplorer-v6-x-released-fully-featured-file-manager.1523691/"
)

_FALLBACK = (
    "Changelog is not available automatically. "
    f"See the [XDA thread]({_XDA_URL}) for full release notes."
)

# Asset/raw paths to search (case-insensitive matching is also applied)
_CANDIDATE_PATHS = [
    "assets/changelog",
    "assets/changelog.txt",
    "assets/CHANGELOG",
    "assets/CHANGELOG.txt",
    "assets/changes",
    "assets/changes.txt",
    "assets/whatsnew",
    "assets/whatsnew.txt",
    "assets/what_is_new.txt",
    "assets/release_notes.txt",
    "res/raw/changelog",
    "res/raw/changes",
    "res/raw/whatsnew",
    "res/raw/release_notes",
]

# String resource keys commonly used for changelogs
_CHANGELOG_KEYS = [
    "changelog", "changes", "whatsnew", "what_is_new",
    "release_notes", "new_features", "version_history",
    "update_log", "update_info",
]


def fetch_changelog(apk_path: Path, version_name: str) -> str:
    """
    Try to extract changelog for *version_name* from *apk_path*.
    Always returns a non-empty string.
    """
    log.info(f"Fetching changelog for v{version_name} from {apk_path.name} …")

    # Method 1: raw file inside APK zip
    result = _from_apk_assets(apk_path, version_name)
    if result:
        log.info(f"  Changelog found in APK assets for v{version_name}")
        return result

    # Method 2: aapt string resources dump
    result = _from_aapt_strings(apk_path, version_name)
    if result:
        log.info(f"  Changelog found via aapt strings for v{version_name}")
        return result

    log.info(f"  No changelog found in APK for v{version_name} — using fallback")
    return _FALLBACK


def _from_apk_assets(apk_path: Path, version_name: str) -> Optional[str]:
    """Search APK zip for changelog text files."""
    try:
        with zipfile.ZipFile(apk_path, "r") as zf:
            # Build lower-case lookup
            names_map = {n.lower(): n for n in zf.namelist()}

            # Check known candidate paths
            for candidate in _CANDIDATE_PATHS:
                actual = names_map.get(candidate.lower())
                if actual:
                    try:
                        raw = zf.read(actual).decode("utf-8", errors="replace").strip()
                        if len(raw) > 20:
                            section = _extract_version_section(raw, version_name)
                            return _format_changelog(section or raw[:3000])
                    except Exception:
                        continue

            # Case-insensitive broad search for any changelog-like file
            for lower_name, actual_name in names_map.items():
                basename = lower_name.split("/")[-1].rstrip(".txt").rstrip(".md")
                if basename in _CHANGELOG_KEYS:
                    try:
                        raw = zf.read(actual_name).decode("utf-8", errors="replace").strip()
                        if len(raw) > 20:
                            section = _extract_version_section(raw, version_name)
                            return _format_changelog(section or raw[:3000])
                    except Exception:
                        continue

    except Exception as exc:
        log.debug(f"APK asset search failed for {apk_path.name}: {exc}")

    return None


def _from_aapt_strings(apk_path: Path, version_name: str) -> Optional[str]:
    """Use aapt to dump string resources and search for changelog content."""
    try:
        result = subprocess.run(
            [AAPT_PATH, "dump", "--values", "resources", str(apk_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            return None

        output = result.stdout

        # Search for any string resource containing changelog-like keys
        for key in _CHANGELOG_KEYS:
            # Pattern: (string8) "key" = "value"
            # or: "key" with indented content following
            pattern = re.compile(
                rf'(?:string[0-9]*).*?["\'](?:[^"\']*{key}[^"\']*)["\']'
                rf'[^\n]*\n\s*["\']([^"\']+)["\']',
                re.IGNORECASE,
            )
            m = pattern.search(output)
            if m:
                content = m.group(1).strip()
                if len(content) > 20:
                    section = _extract_version_section(content, version_name)
                    return _format_changelog(section or content[:3000])

    except Exception as exc:
        log.debug(f"aapt string dump failed for {apk_path.name}: {exc}")

    return None


def _extract_version_section(text: str, version_name: str) -> Optional[str]:
    """
    Try to find and return the section of *text* that corresponds to
    *version_name*. Returns None if no version-specific section found.
    """
    # Look for lines starting with the version number or v+version
    pattern = re.compile(
        rf'^[v\s]*{re.escape(version_name)}[^\n]*$',
        re.IGNORECASE | re.MULTILINE,
    )
    match = pattern.search(text)
    if not match:
        return None

    start = match.start()
    # Find the next version header (or end of text)
    next_version = re.compile(
        r'^[v\s]*\d+\.\d+',
        re.MULTILINE,
    )
    next_match = next_version.search(text, match.end() + 1)
    end = next_match.start() if next_match else len(text)

    section = text[start:end].strip()
    return section if len(section) > 10 else None


def _format_changelog(text: str) -> str:
    """
    Normalize changelog text to Markdown bullet list format.
    Preserves existing bullet characters, normalises them to `- `.
    """
    if not text:
        return _FALLBACK

    lines = text.splitlines()
    formatted = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Normalise common bullet variants
        stripped = re.sub(r'^[-•*·▪▸➤→\u2022]\s*', '- ', stripped)
        # If no bullet, check if it looks like a list item
        if not stripped.startswith('- ') and not stripped.startswith('#'):
            stripped = f"- {stripped}"
        formatted.append(stripped)

    result = "\n".join(formatted)
    return result if result else _FALLBACK
