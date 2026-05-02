"""
Best-effort changelog fetcher for MiXplorer releases.

Strategy:
  1. Try to fetch the first post of the XDA forum thread.
  2. Look for version-specific changelog markers in the text.
  3. Fall back gracefully — always returns a usable string.

This module never raises. A failed fetch returns a polite fallback message.
"""
import re
import time
from typing import Optional

import requests

from logger import get_logger

log = get_logger(__name__)

_XDA_THREAD_URL = (
    "https://xdaforums.com/t/"
    "app-2-2-mixplorer-v6-x-released-fully-featured-file-manager.1523691/"
)

_FALLBACK = (
    "Changelog is not available automatically. "
    "See the [XDA forum thread]({url}) for full release notes."
).format(url=_XDA_THREAD_URL)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_TIMEOUT = 20  # seconds


def fetch_xda_changelog(version_name: str) -> str:
    """
    Attempt to extract the changelog for *version_name* from the XDA thread.

    Returns a Markdown-formatted string always (never raises).
    """
    try:
        resp = requests.get(
            _XDA_THREAD_URL,
            headers=_HEADERS,
            timeout=_TIMEOUT,
            allow_redirects=True,
        )
        if resp.status_code != 200:
            log.warning(f"XDA fetch returned HTTP {resp.status_code}")
            return _FALLBACK

        text = resp.text

        # Try to find a changelog block near the version string
        # Developer typically writes "v6.70.3" or "6.70.3" followed by changes
        pattern = re.compile(
            rf'(?:v\s*)?{re.escape(version_name)}[^\n]*\n((?:[-•*\u2022].+\n?)+)',
            re.IGNORECASE | re.MULTILINE,
        )
        match = pattern.search(text)
        if match:
            raw = match.group(1).strip()
            # Convert bullet variants to markdown list
            lines = [
                re.sub(r'^[-•*\u2022]\s*', '- ', line.strip())
                for line in raw.splitlines()
                if line.strip()
            ]
            if lines:
                log.info(f"XDA changelog found for v{version_name}: {len(lines)} item(s)")
                return "\n".join(lines)

        log.info(f"No structured changelog found on XDA for v{version_name} — using fallback")
        return _FALLBACK

    except requests.RequestException as exc:
        log.warning(f"XDA fetch failed: {exc}")
        return _FALLBACK
    except Exception as exc:
        log.warning(f"Unexpected error in changelog fetch: {exc}")
        return _FALLBACK
