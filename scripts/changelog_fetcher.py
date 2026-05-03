"""
Changelog fetcher — APKMirror release pages.

URL pattern (APKMirror):
  https://www.apkmirror.com/apk/{dev-slug}/{app-slug}/{release-slug}-release/#whatsnew

The "What's New" content sits inside the element with id="whatsnew" on the release page.
It is plain HTML, no JavaScript rendering needed.

Strategy:
  1. Build the release page URL from app_name + version_name.
  2. Fetch the page and parse the #whatsnew section.
  3. If anything fails (HTTP error, parse failure, timeout) → return None.
     Callers must treat None as "no changelog available" and omit it silently.
"""
import re
import time
from pathlib import Path
from typing import Optional

import requests

from logger import get_logger

log = get_logger(__name__)

_BASE = "https://www.apkmirror.com"

# Per-app configuration:
#   "app-slug"      : the folder slug in the APKMirror URL
#   "release-prefix": the slug prefix used in the release page URL
#   (most apps use the same value for both; Codecs is the exception)
_APP_CONFIG: dict[str, dict] = {
    "MiXplorer":   {"slug": "mixplorer-hootanparsa",  "prefix": "mixplorer"},
    "MiX_Archive": {"slug": "mix-archive",             "prefix": "mix-archive"},
    "MiX_Codecs":  {"slug": "mix-codecs",              "prefix": "mix-codecs-mixplorer-addon"},
    "MiX_Encrypt": {"slug": "mix-encrypt",             "prefix": "mix-encrypt"},
    "MiX_Image":   {"slug": "mix-image",               "prefix": "mix-image"},
    "MiX_PDF":     {"slug": "mix-pdf",                 "prefix": "mix-pdf"},
    "MiX_Tagger":  {"slug": "mix-tagger",              "prefix": "mix-tagger"},
}

_DEV_SLUG = "hootan-parsa"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Mobile Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.apkmirror.com/",
}

_TIMEOUT = 20


def _version_to_slug(version_name: str) -> str:
    """'6.70.3' → '6-70-3',  '1.0' → '1-0',  '2.9' → '2-9'"""
    return version_name.replace(".", "-")


def _derive_app_slug(app_name: str) -> str:
    """
    For unknown future add-ons, derive a best-guess APKMirror app slug.

    Rule: 'MiX_NewName' → 'mix-newname'  (lowercase, underscore→hyphen)
    """
    return app_name.lower().replace("_", "-")


def _build_url(app_name: str, version_name: str) -> str:
    """Build the APKMirror release page URL for the given app and version."""
    ver = _version_to_slug(version_name)

    if app_name in _APP_CONFIG:
        cfg    = _APP_CONFIG[app_name]
        slug   = cfg["slug"]
        prefix = cfg["prefix"]
    else:
        # Future add-on — auto-derive
        slug   = _derive_app_slug(app_name)
        prefix = slug

    return f"{_BASE}/apk/{_DEV_SLUG}/{slug}/{prefix}-{ver}-release/"


def _fetch_whatsnew(url: str) -> Optional[str]:
    """
    Fetch *url* and extract the text content of the #whatsnew section.
    Returns the raw text block or None on any failure.
    """
    try:
        time.sleep(1.5)  # polite delay
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT, allow_redirects=True)

        if resp.status_code == 404:
            log.debug(f"  APKMirror 404: {url}")
            return None
        if resp.status_code != 200:
            log.warning(f"  APKMirror HTTP {resp.status_code}: {url}")
            return None

        return _parse_whatsnew(resp.text)

    except requests.RequestException as exc:
        log.warning(f"  APKMirror fetch error: {exc}")
        return None


def _parse_whatsnew(html: str) -> Optional[str]:
    """
    Extract the What's New text from APKMirror's release page HTML.

    APKMirror uses:  <div ... id="whatsnew">...</div>
    The content is plain text bullet points separated by <br> tags.
    """
    # Find the whatsnew div by id
    m = re.search(
        r'id=["\']whatsnew["\'][^>]*>(.*?)</div>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if not m:
        # Broader fallback: look for a <section> or any block containing #whatsnew anchor
        m = re.search(
            r'(?:whatsnew|what.s.new)[^>]*>\s*<[^>]+>(.*?)</(?:div|section|p)>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
    if not m:
        return None

    raw = m.group(1)
    return _clean_html(raw)


def _clean_html(raw: str) -> Optional[str]:
    """
    Convert raw HTML snippet to clean Markdown bullet list.
    Handles <br>, <p>, bullet characters.
    """
    # Replace <br> and <p> variants with newlines
    text = re.sub(r"<br\s*/?>", "\n", raw, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<p[^>]*>", "", text, flags=re.IGNORECASE)
    # Strip remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode HTML entities
    text = (text
            .replace("&bull;", "•")
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&#8226;", "•")
            .replace("&nbsp;", " "))
    text = re.sub(r"\s+", " ", text)

    # Split into lines on bullet characters or newlines
    lines = []
    for chunk in re.split(r"[\n\r]+|(?=\s*[•\-\*·▪])", text):
        chunk = chunk.strip()
        chunk = re.sub(r"^[•\-\*·▪▸➤→\u2022]\s*", "", chunk).strip()
        if len(chunk) > 3:
            lines.append(f"- {chunk}")

    if not lines:
        return None

    return "\n".join(lines)


def fetch_changelog(apk_path: Path, version_name: str, app_name: str = "MiXplorer") -> Optional[str]:
    """
    Fetch changelog for *app_name* version *version_name* from APKMirror.

    Returns a Markdown-formatted string on success, None if unavailable.
    Callers should treat None as "omit changelog section" — never show an error message.
    """
    url = _build_url(app_name, version_name)
    log.info(f"Fetching changelog: {app_name} v{version_name} → {url}")

    result = _fetch_whatsnew(url)
    if result:
        log.info(f"  Changelog found ({len(result.splitlines())} line(s))")
    else:
        log.info(f"  No changelog found for {app_name} v{version_name} — will be omitted")

    return result
