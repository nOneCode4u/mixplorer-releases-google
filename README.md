# MiXplorer Releases

> Automated mirror of **[MiXplorer](https://xdaforums.com/t/app-2-2-mixplorer-v6-x-released-fully-featured-file-manager.1523691/)** and all its official add-on plugins by [H. Parsa](https://xdaforums.com/m/hootan-parsa.3515296/), sourced directly from the developer's Google Drive. Releases are checked and updated daily.

[![Total Downloads](https://img.shields.io/github/downloads/nOneCode4u/mixplorer-releases-google/total?style=for-the-badge&logo=android&logoColor=white&color=3DDC84)](https://github.com/nOneCode4u/mixplorer-releases-google/releases)
[![Latest Release](https://img.shields.io/github/v/release/nOneCode4u/mixplorer-releases-google?style=for-the-badge&logo=github&color=0969da&label=Latest)](https://github.com/nOneCode4u/mixplorer-releases-google/releases/latest)
[![Update Check](https://img.shields.io/github/actions/workflow/status/nOneCode4u/mixplorer-releases-google/daily_update.yml?style=for-the-badge&label=Daily%20Update&logo=githubactions&logoColor=white)](https://github.com/nOneCode4u/mixplorer-releases-google/actions)

[![Get it on Obtainium](https://github.com/ImranR98/Obtainium/raw/main/assets/graphics/badge_obtainium.png)](https://github.com/nOneCode4u/mixplorer-releases-google/releases)

---

## Available Apps

All APKs below are the original, unmodified releases published by the developer.

| App | Description | Download |
|-----|-------------|----------|
| 📁 **[MiXplorer](https://github.com/nOneCode4u/mixplorer-releases-google/releases?q=MiXplorer-v)** | Powerful dual-pane file manager with cloud, archive, and media support | [Latest →](https://github.com/nOneCode4u/mixplorer-releases-google/releases?q=MiXplorer-v) |
| 🗜️ **[MiX Archive](https://github.com/nOneCode4u/mixplorer-releases-google/releases?q=MiX_Archive-v)** | Archive plugin — ZIP, RAR, RAR5, 7z, TAR, GZ and more | [Latest →](https://github.com/nOneCode4u/mixplorer-releases-google/releases?q=MiX_Archive-v) |
| 🎵 **[MiX Codecs](https://github.com/nOneCode4u/mixplorer-releases-google/releases?q=MiX_Codecs-v)** | Extended audio/video codec plugin for the built-in media player | [Latest →](https://github.com/nOneCode4u/mixplorer-releases-google/releases?q=MiX_Codecs-v) |
| 🔐 **[MiX Encrypt](https://github.com/nOneCode4u/mixplorer-releases-google/releases?q=MiX_Encrypt-v)** | File encryption and decryption plugin | [Latest →](https://github.com/nOneCode4u/mixplorer-releases-google/releases?q=MiX_Encrypt-v) |
| 🖼️ **[MiX Image](https://github.com/nOneCode4u/mixplorer-releases-google/releases?q=MiX_Image-v)** | Image viewer plugin with wide format support | [Latest →](https://github.com/nOneCode4u/mixplorer-releases-google/releases?q=MiX_Image-v) |
| 📄 **[MiX PDF](https://github.com/nOneCode4u/mixplorer-releases-google/releases?q=MiX_PDF-v)** | PDF viewer plugin — read documents without leaving MiXplorer | [Latest →](https://github.com/nOneCode4u/mixplorer-releases-google/releases?q=MiX_PDF-v) |
| 🏷️ **[MiX Tagger](https://github.com/nOneCode4u/mixplorer-releases-google/releases?q=MiX_Tagger-v)** | Audio tag editor — ID3, Vorbis, APE, artwork and batch edit | [Latest →](https://github.com/nOneCode4u/mixplorer-releases-google/releases?q=MiX_Tagger-v) |

---

## Using with Obtainium

[Obtainium](https://github.com/ImranR98/Obtainium) is an Android app that tracks GitHub releases and updates your apps automatically — no Play Store needed.

**To add any app from this mirror to Obtainium:**

1. Install [Obtainium](https://github.com/ImranR98/Obtainium/releases) on your Android device.
2. Open Obtainium → tap **"Add App"**.
3. Paste the URL for the app you want:

   | App | Obtainium URL |
   |-----|---------------|
   | MiXplorer | `https://github.com/nOneCode4u/mixplorer-releases-google` |
   | MiX Archive | `https://github.com/nOneCode4u/mixplorer-releases-google` |
   | MiX Codecs | `https://github.com/nOneCode4u/mixplorer-releases-google` |
   | MiX Encrypt | `https://github.com/nOneCode4u/mixplorer-releases-google` |
   | MiX Image | `https://github.com/nOneCode4u/mixplorer-releases-google` |
   | MiX PDF | `https://github.com/nOneCode4u/mixplorer-releases-google` |
   | MiX Tagger | `https://github.com/nOneCode4u/mixplorer-releases-google` |

4. Under **"Additional Options"**, set the **release tag filter** to the app name (e.g. `MiXplorer-v`) so Obtainium only tracks that specific app's releases.
5. Tap **"Add"**. Obtainium will now notify you and update the app automatically.

---

## Which APK Should I Download?

Each app release includes multiple APK variants for different CPU architectures.

| Filename Suffix | Architecture | Who should use this? |
|---|---|---|
| *(no suffix)* | Universal / Pure-Java | All devices — works everywhere |
| `-arm` | 32-bit ARM | Older Android phones (before 2016) |
| `-arm64` ⭐ | 64-bit ARM | **Most modern Android phones — recommended** |
| `-x86` | 32-bit x86 | Older emulators |
| `-x64` | 64-bit x86 | Modern emulators and Intel Chromebooks |
| `-universal` | All architectures | Any device (largest file size) |

**Quick rule:** If you are unsure, always download the **`-arm64`** variant. It works on virtually all Android smartphones made since 2016.

---

## Why This Repository Exists

MiXplorer and its plugins are developed by H. Parsa and distributed via the [XDA forum thread](https://xdaforums.com/t/app-2-2-mixplorer-v6-x-released-fully-featured-file-manager.1523691/) and a private Google Drive folder. While the apps are excellent, the existing distribution channels have a few practical drawbacks:

- The XDA thread requires manual checking for new versions.
- The in-app updater for MiXplorer downloads the APK but does not remove the file afterwards — this wastes storage over time.
- There is no single place to find all plugins and all APK variants in one location.
- Tools like Obtainium cannot track XDA threads natively.

This repository solves all of those problems by automatically mirroring the official APK releases to GitHub on a daily schedule.

---

## Notes & Disclaimer

- All APKs hosted here are original and unmodified. No patches, cracks, or alterations of any kind are applied.
- This is an **unofficial mirror** maintained by an independent contributor. It is not affiliated with, endorsed by, or sponsored by H. Parsa or the MiXplorer project.
- If the developer requests removal of any content, it will be done promptly.
- For official support, feature requests, or to thank the developer, visit the [XDA thread](https://xdaforums.com/t/app-2-2-mixplorer-v6-x-released-fully-featured-file-manager.1523691/).

---

## Credits

All apps in this repository are designed, developed, and maintained by **H. Parsa (Hootan Parsa)**.  
All credit for the applications belongs entirely to the original developer.

---

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=nOneCode4u/mixplorer-releases-google&type=Date)](https://star-history.com/#nOneCode4u/mixplorer-releases-google&Date)
