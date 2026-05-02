"""
Changelog fetcher for MiXplorer and add-ons.

Sources (in priority order):
  1. APKMirror release page — "APK Notes" section
     Parses the plain-text changelog the developer publishes with each upload.
  2. APK zip assets — searches the APK's bundled asset files
  3. Fallback — a short message with source link
"""
import os
import re
import time
import zipfile
from pathlib import Path
from typing import Optional

import requests

from logger import get_logger

log = get_logger(__name__)

AAPT_PATH: str = os.environ.get("AAPT_PATH", "aapt")

# APKMirror app slugs per app_name key
_APKMIRROR_SLUGS: dict[str, str] = {
    "MiXplorer":  "hootan-parsa/mixplorer-hootanparsa",
    "MiX_Archive": "hootan-parsa/mix-archive",
    "MiX_Codecs":  "hootan-parsa/mix-codecs",
    "MiX_Encrypt": "hootan-parsa/mix-encrypt",
    "MiX_Image":   "hootan-parsa/mix-image",
    "MiX_PDF":     "hootan-parsa/mix-pdf",
    "MiX_Tagger":  "hootan-parsa/mix-tagger",
}

_APKMIRROR_BASE = "https://www.apkmirror.com"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Mobile Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.apkmirror.com/",
}

_TIMEOUT = 20

_XDA_URL = (
    "https://xdaforums.com/t/"
    "app-2-3-mixplorer-v6-x-released-fully-featured-file-manager.1523691/"
    "post-23374098"
)

_ASSET_PATHS = [
    "assets/changelog", "assets/changelog.txt", "assets/CHANGELOG",
    "assets/changes", "assets/changes.txt", "assets/whatsnew",
    "assets/whatsnew.txt", "assets/release_notes.txt",
    "res/raw/changelog", "res/raw/changes", "res/raw/whatsnew",
]

_CHANGELOG_KEYWORDS = [
    "changelog", "changes", "whatsnew", "what_is_new", "release_notes",
]


def fetch_changelog(apk_path: Path, version_name: str, app_name: str = "MiXplorer") -> str:
    """
    Fetch changelog for *version_name*. Always returns a non-empty string.
    """
    log.info(f"Fetching changelog: {app_name} v{version_name}")

    # 1. APKMirror
    result = _from_apkmirror(app_name, version_name)
    if result:
        return result

    # 2. APK assets
    result = _from_apk_assets(apk_path, version_name)
    if result:
        return result

    # 3. Fallback
    log.info(f"  No changelog found for {app_name} v{version_name} — using fallback")
    slug = _APKMIRROR_SLUGS.get(app_name)
    if slug:
        url = f"{_APKMIRROR_BASE}/apk/{slug}/"
        return f"See [APKMirror]({url}) for release notes."
    return f"See the [XDA thread]({_XDA_URL}) for release notes."


def _apkmirror_release_url(slug: str, version_name: str) -> str:
    """
    Build the APKMirror release page URL.
    Pattern: /apk/{slug}/{app-slug}-{version}-release/
    The app slug is the last part of the developer/app path.
    Version dots are kept as-is (APKMirror uses dashes for some, dots for others).
    We try both formats.
    """
    app_slug = slug.split("/")[-1]
    # APKMirror release URLs use the version with dots replaced by dashes
    ver_dashes = version_name.replace(".", "-")
    return (
        f"{_APKMIRROR_BASE}/apk/{slug}/"
        f"{app_slug}-{ver_dashes}-release/"
    )


def _from_apkmirror(app_name: str, version_name: str) -> Optional[str]:
    """Fetch the APK Notes section from APKMirror for the given version."""
    slug = _APKMIRROR_SLUGS.get(app_name)
    if not slug:
        return None

    url = _apkmirror_release_url(slug, version_name)
    log.debug(f"  APKMirror URL: {url}")

    try:
        time.sleep(2)   # Polite delay — avoid rate limiting
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT, allow_redirects=True)

        if resp.status_code == 404:
            log.info(f"  APKMirror: no page for {app_name} v{version_name} (404)")
            return None
        if resp.status_code != 200:
            log.warning(f"  APKMirror returned HTTP {resp.status_code} for {url}")
            return None

        return _parse_apkmirror_notes(resp.text, version_name)

    except requests.RequestException as exc:
        log.warning(f"  APKMirror fetch failed: {exc}")
        return None


def _parse_apkmirror_notes(html: str, version_name: str) -> Optional[str]:
    """
    Extract the 'APK Notes' / changelog section from APKMirror HTML.

    APKMirror stores notes in a <div class="apk-notes"> or inside
    a <div class="notes"> block as plain text with • bullets.
    The content is in the page source without requiring JavaScript.
    """
    # Try to find the notes block
    # APKMirror pattern: "APK Notes:" or "From version X.Y.Z:" followed by bullet points
    patterns = [
        # Standard notes div
        r'class="apk-notes"[^>]*>(.*?)</div>',
        r'class="notes"[^>]*>(.*?)</div>',
        # "From version X.Y.Z:" heading in the notes
        r'(?:From version|APK Notes:?)[^<]*(?:</[^>]+>)?\s*<p[^>]*>(.*?)</p>',
        # Plain bullet section
        r'(?:v' + re.escape(version_name) + r'[^:]*:?)((?:\s*[•\-\*].+)+)',
    ]

    for pattern in patterns:
        m = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if m:
            raw = m.group(1)
            cleaned = _clean_html_notes(raw, version_name)
            if cleaned and len(cleaned) > 20:
                log.info(f"  APKMirror: changelog extracted ({len(cleaned)} chars)")
                return cleaned

    # Broader fallback: look for version number followed by bullet points anywhere
    ver_pattern = re.compile(
        rf'v{re.escape(version_name)}'
        rf'[_\w]*:?\s*\n?((?:\s*[•\-\*].+\n?)+)',
        re.IGNORECASE,
    )
    m = ver_pattern.search(html)
    if m:
        cleaned = _clean_html_notes(m.group(1), version_name)
        if cleaned:
            log.info(f"  APKMirror: version-matched changelog extracted")
            return cleaned

    log.info(f"  APKMirror: page found but no parseable notes for v{version_name}")
    return None


def _clean_html_notes(raw: str, version_name: str) -> Optional[str]:
    """Strip HTML tags, normalise bullets, return Markdown list or None."""
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", raw)
    # Decode common HTML entities
    text = (text.replace("&bull;", "•").replace("&amp;", "&")
                .replace("&lt;", "<").replace("&gt;", ">")
                .replace("&#8226;", "•").replace("&nbsp;", " "))
    text = re.sub(r"\s+", " ", text).strip()

    lines = []
    for part in re.split(r"(?=[•\-\*])", text):
        part = part.strip()
        if not part:
            continue
        part = re.sub(r"^[•\-\*]\s*", "", part).strip()
        if len(part) > 3:
            lines.append(f"- {part}")

    return "\n".join(lines) if lines else None


def _from_apk_assets(apk_path: Path, version_name: str) -> Optional[str]:
    """Search APK zip for changelog text files in assets/ or res/raw/."""
    try:
        with zipfile.ZipFile(apk_path, "r") as zf:
            names_map = {n.lower(): n for n in zf.namelist()}
            for candidate in _ASSET_PATHS:
                actual = names_map.get(candidate.lower())
                if not actual:
                    continue
                try:
                    raw = zf.read(actual).decode("utf-8", errors="replace").strip()
                    if len(raw) > 20:
                        section = _extract_version_section(raw, version_name)
                        result = _format_text_changelog(section or raw[:3000])
                        if result:
                            return result
                except Exception:
                    continue

            # Broad keyword search
            for lower_name, actual_name in names_map.items():
                basename = lower_name.split("/")[-1]
                basename = re.sub(r'\.(txt|md)$', '', basename)
                if basename in _CHANGELOG_KEYWORDS:
                    try:
                        raw = zf.read(actual_name).decode("utf-8", errors="replace").strip()
                        if len(raw) > 20:
                            section = _extract_version_section(raw, version_name)
                            return _format_text_changelog(section or raw[:3000])
                    except Exception:
                        continue
    except Exception as exc:
        log.debug(f"APK asset search failed: {exc}")
    return None


_CHANGELOG_KEYWORDS = {
    "changelog", "changes", "whatsnew", "what_is_new",
    "release_notes", "new_features", "update_log",
}


def _extract_version_section(text: str, version_name: str) -> Optional[str]:
    pattern = re.compile(
        rf'^[v\s]*{re.escape(version_name)}[^\n]*$',
        re.IGNORECASE | re.MULTILINE,
    )
    match = pattern.search(text)
    if not match:
        return None
    start = match.start()
    next_ver = re.compile(r'^[v\s]*\d+\.\d+', re.MULTILINE)
    next_m = next_ver.search(text, match.end() + 1)
    end = next_m.start() if next_m else len(text)
    section = text[start:end].strip()
    return section if len(section) > 10 else None


def _format_text_changelog(text: str) -> Optional[str]:
    if not text:
        return None
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        stripped = re.sub(r'^[-•*·▪▸➤→\u2022]\s*', '- ', stripped)
        if not stripped.startswith('- ') and not stripped.startswith('#'):
            stripped = f"- {stripped}"
        lines.append(stripped)
    result = "\n".join(lines)
    return result if result else None
