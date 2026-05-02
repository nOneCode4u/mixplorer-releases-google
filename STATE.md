# Workflow State

<!-- STATE: Error -->

| Key | Value |
|-----|-------|
| **Last Updated** | 2026-05-02 05:59:34 UTC |
| **Last Status**  | Unexpected error in MiXplorer |
| **Details**      | PosixPath('/tmp/apk_update_k2uh4va6/MiXplorer/MiXplorer_v6.70.3_B26022811-arm.apk') and PosixPath('/tmp/apk_update_k2uh4va6/MiXplorer/MiXplorer_v6.70.3_B26022811-arm.apk') are the same file |

---

## Control Reference

### Resume After Pause
1. Resolve the open GitHub Issue that describes the problem.
2. If version extraction failed, fill in `MANUAL_VERSIONS.md`.
3. Change **`Paused`** → **`Resumed`** in the HTML comment above (line 3).
4. The next scheduled run will execute, then auto-reset to `Running`.

### Force a Manual Run
Go to **Actions → Daily APK Update Check → Run workflow**.

### State Definitions
| State | Meaning |
|-------|---------|
| `Running`  | Normal — scheduled runs active |
| `Paused`   | Manual intervention required — see linked Issue |
| `Resumed`  | Will execute once, then auto-reset to `Running` |
| `Error`    | Critical failure — inspect Actions logs |
