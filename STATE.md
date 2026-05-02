# Workflow State

<!-- STATE: Running -->

| Key | Value |
|-----|-------|
| **Last Updated** | — |
| **Last Status**  | — |
| **Details**      | — |

---

## Control

**To resume after a failure:** fix the issue → change `Paused` → `Resumed` above → save.

**To force a full re-run:** Actions → Daily APK Update Check → Run workflow → enable "Force re-process all apps".

**To set up `GDRIVE_API_KEY`:**
1. Go to [Google Cloud Console](https://console.cloud.google.com/) → create a project.
2. Enable **Google Drive API**.
3. Credentials → **+ CREATE CREDENTIALS** → **API key** → restrict to Google Drive API.
4. In this repo: Settings → Secrets → Actions → New repository secret → `GDRIVE_API_KEY`.

| State | Meaning |
|-------|---------|
| `Running` | Normal — daily runs active |
| `Paused` | Fix required — see open issue |
| `Resumed` | Will run once, then resets to `Running` |
| `Error` | Check Actions log |
