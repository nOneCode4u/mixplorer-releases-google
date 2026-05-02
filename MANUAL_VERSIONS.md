# Manual Version Overrides

> When APK version extraction fails, the pipeline pauses and opens a GitHub Issue.
> Fill in this file, then set `STATE.md` to `Resumed`.

**How:** Download the APK → run `aapt dump badging filename.apk` → note `versionName` and `versionCode`.
**arch values:** `java`, `arm`, `arm64`, `x86`, `x64`, `universal`

## Pending

| Filename | versionName | versionCode | arch | App |
|---|---|---|---|---|
