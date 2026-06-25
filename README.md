# MemoryBox

![MemoryBox Screenshot](docs/screenshot.png)

MemoryBox is a native Mac desktop app that takes a folder of trip or event photos, automatically groups burst shots using perceptual hashing, and picks the single best photo from each group using Claude Vision AI. The result is a curated folder of keepers — no terminal required.

## Download

Grab the latest build from the [Releases page](https://github.com/arpit-jaiswal/memorybox/releases/latest) and download `MemoryBox-mac.zip`.

## First launch on Mac

macOS Gatekeeper will warn you because the app is not code-signed with an Apple Developer certificate. To open it:

1. Right-click `MemoryBox.app` → **Open**
2. Click **Open** in the dialog

You only need to do this once.

## Setup

1. Open MemoryBox
2. Paste your Anthropic API key in the **Anthropic API Key** field (get one at [console.anthropic.com](https://console.anthropic.com))
3. The key is saved securely in your macOS Keychain — you only type it once

No terminal needed.

## Development setup

```bash
git clone https://github.com/arpit-jaiswal/memorybox
cd memorybox
pip install -r requirements.txt -r requirements-dev.txt
python run.py          # run in dev mode
bash build_mac.sh      # build .app locally
```

## Tech stack

- **Python** — core language
- **CustomTkinter** — native-feeling dark UI
- **Anthropic Claude Vision** — AI photo scoring
- **imagehash** — perceptual hash grouping
- **Pillow + pillow-heif** — image loading (HEIC/JPEG/PNG/TIFF)
- **open-clip-torch** — CLIP re-clustering for large bursts
- **keyring** — secure API key storage in macOS Keychain
- **PyInstaller** — `.app` bundle packaging

## Roadmap

- Video clip extraction (coming soon)
