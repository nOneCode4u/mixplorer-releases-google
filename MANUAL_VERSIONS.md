# Manual Version Overrides

> **When to use this file:**  
> When automatic APK version extraction fails, the pipeline will pause and create a GitHub Issue.  
> Fill in the `FILL_ME` cells below, then change `STATE.md` from `Paused` → `Resumed`.

---

## Instructions

1. Find the failing APK entry in the **Pending** table.
2. Determine the correct values:
   - Download the APK and run: `aapt dump badging filename.apk`
   - Or use any APK analyser app on Android (e.g. APK Analyser, JADX).
   - Note the `versionName` (e.g. `6.70.3`) and `versionCode` (e.g. `26022810`).
3. Replace `FILL_ME` in the table with the actual values.
4. For `arch`, use one of: `java`, `arm`, `arm64`, `x86`, `x64`, `universal`.
5. Save this file.
6. Open `STATE.md` and change `Paused` → `Resumed` in line 3.

---

## Pending (Fill these in)

| Filename | versionName | versionCode | arch | App |
|---|---|---|---|---|

---

## Completed Entries

| Filename | versionName | versionCode | arch | App |
|---|---|---|---|---|
