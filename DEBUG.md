# Debug Guide

This document explains how to diagnose issues, enable verbose logging, and set up required secrets.

---

## Quick Actions

| Problem | Action |
|---------|--------|
| Workflow is paused | Check open Issues → fix → set `STATE.md` to `Resumed` |
| Version extraction failed | Fill in `MANUAL_VERSIONS.md` → set `STATE.md` to `Resumed` |
| Want to force re-release everything | Actions → Run workflow → enable **"Force re-process all apps"** |
| Want to see detailed logs | Actions → Run workflow → enable **"Enable verbose debug logging"** |

---

## Enabling Debug Mode

### Option A — Manual Trigger (Recommended)
1. Go to the **Actions** tab.
2. Select **Daily APK Update Check**.
3. Click **Run workflow** (top right of the workflow list).
4. Enable **"Enable verbose debug logging"**.
5. Click **Run workflow**.

All `DEBUG`-level messages will appear in the Actions console output.

### Option B — Log Files
After every run, a timestamped log file is committed to the `logs/` directory.  
Browse `logs/` to find the latest run's full debug output.

---

## Required Secrets

| Secret Name | Description | Required |
|-------------|-------------|----------|
| `GDRIVE_API_KEY` | Google Drive API v3 key | ✅ Yes |
| `GITHUB_TOKEN` | Auto-provided by Actions | ✅ Auto |

### Setting Up `GDRIVE_API_KEY`

1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create or select a project.
3. Navigate to **APIs & Services → Enable APIs** → enable **Google Drive API**.
4. Go to **APIs & Services → Credentials → Create Credentials → API Key**.
5. Click **Restrict Key**:
   - Under **API restrictions**, select **Restrict key** → choose **Google Drive API**.
   - Save.
6. Copy the API key.
7. In this repository: **Settings → Secrets and variables → Actions → New repository secret**.
   - Name: `GDRIVE_API_KEY`
   - Value: *(paste your key)*

---

## Common Error Messages

### `GDRIVE_API_KEY secret is not configured`
The secret is missing. Follow the setup steps above.

### `Drive 403: …`
The API key is invalid, expired, or the Drive folder is no longer public.
Verify both the key and the folder permissions.

### `MD5 mismatch for filename.apk`
The downloaded file is corrupted. The pipeline retries automatically (3×).
If it persists, the Drive file itself may be corrupted — check the source.

### `All extraction methods failed`
The APK cannot be parsed by any method. Use `MANUAL_VERSIONS.md` to provide the version manually.

### `Verification FAILED — missing assets`
Upload succeeded partially. Check the release on GitHub and upload missing files manually,
or delete the release and set `STATE.md` → `Resumed` to let the pipeline retry.

---

## Manual Workflow Control

### Pause
Set `STATE.md` line 3: `<!-- STATE: Paused -->`

### Resume
Set `STATE.md` line 3: `<!-- STATE: Resumed -->`

### Force a Full Re-run
Actions → Run workflow → enable **"Force re-process all apps"** → Run.
