# Key Design Decisions

This document captures architectural decisions for Photobox. For detailed design rationale, see [DESIGN.md](DESIGN.md).

## Web Installer

**Decision:** Prepare configured Photobox images locally in the browser, then use Raspberry Pi Imager to write them to SD cards.

**Why:**
- Users select WiFi country and optional boot debug before saving the image
- Image preparation runs locally without uploading the user's settings
- Raspberry Pi Imager provides native SD card access; browsers cannot write raw images to standard SD card readers

**Platform:** React + TypeScript + Vite, compiled to static HTML/CSS/JS and deployed to GitHub Pages at https://fylke.github.io/photobox/installer

**Supported platforms:**
- Raspberry Pi 3 (armv7l)
- Raspberry Pi 4 (aarch64)
- Raspberry Pi 5 (aarch64)

**Supported countries:** See `installer/src/config.ts` for WiFi regulatory domains selected during image preparation.

**Deployment:**
- Source code: `installer/` at repository root
- Built artifacts: `docs/installer/` (deployed by GitHub Pages workflow)
- GitHub Actions workflow: `.github/workflows/pages.yml`

**Constraints:**
- Image preparation requires a current browser with File System Access and origin-private file system support
- Use a regular browser window and allow several gigabytes of free local disk space
- Raspberry Pi Imager must be installed to write the prepared `.img` file using **Use custom**
- Boot debug requires a base image containing the boot-debug service

## Raspberry Pi Image

**Decision:** Build minimal Pi OS images with Photobox preinstalled for Pi 3, 4, and 5.

**Why:**
- Single pre-configured image for reliable first-boot setup
- Users don't need to install Photobox manually
- Minimal image (no desktop) reduces SD card requirements and boot time
- Image build is deterministic and reproducible via CI

**Build process:**
- CI builds on ARM hardware (Raspberry Pi OS)
- Uses pi-gen (official Raspberry Pi OS builder) as base
- Only stages 0, 1, and custom photobox stage (no desktop/GUI)
- Output: compressed `.img.xz` file with SHA256 checksums

**Image characteristics:**
- Headless (no X11, no desktop environment)
- Command-line only with systemd services
- Boots directly to Photobox daemon (no login prompt)

**First-boot behavior:**
- Opens temporary open WiFi network (`Photobox Setup`)
- Admin claims booth via web UI on `10.42.0.1:8000`
- Admin switches to private hotspot and configures venue WiFi (optional)
- Photobox daemon runs as systemd service

**WiFi regulatory domain:**
- Set in the image's boot command line during browser preparation
- Prevents regulatory violations in different countries
- Embedded in OS image for reliability

## Setup and Pairing

**Decision:** All setup occurs via phone or local device; no cloud dependencies.

**Primary setup path:**
1. Prepare and save an image in the web installer (select WiFi country and optional boot debug)
2. Write the saved `.img` with Raspberry Pi Imager using **Use custom**
3. Boot Pi, connect to `Photobox Setup` network
4. Admin claims booth via `10.42.0.1:8000`
5. Switch to private hotspot and configure venue WiFi (optional)

**Alternative setup path (development only):**
- Run Photobox daemon on desktop via Python (`photobox-setup-pin` + `photobox` command)
- No hotspot or WiFi management
- Intended for testing and development, not production

**Security model:**
- One-time setup PIN (6 digits, shown once, consumed after use)
- Admin gets `HttpOnly`, `SameSite=Strict` cookie
- Guest invitations with short-lived tokens
- No cloud sync, no account requirements

## Supported Hardware

| Component | Minimum | Tested | Production |
|-----------|---------|--------|-----------|
| **Pi Model** | Pi 3 | Pi 4, Pi 5 | Pi 4, Pi 5 |
| **OS** | Debian Trixie armv7l/aarch64 | Raspberry Pi OS Trixie | Raspberry Pi OS Trixie |
| **Camera** | V4L2 (USB/CSI) | USB webcam | Webcam or CSI camera |
| **Storage** | 4 GB SD card (Pi 3) | microSD card | microSD card |
| **Network** | WiFi or wired | Test network | Private hotspot + optional venue WiFi |

**WiFi regulatory domains:**
Selected in the web installer during image preparation. See `installer/src/config.ts` for full list.

## Development

**Installer:**
- **Language:** TypeScript + React 18
- **Build tool:** Vite
- **Dev server:** `npm run dev` on http://localhost:5173
- **Build:** `npm run build` outputs to `dist/`
- **Size:** ~165 KB (uncompressed), ~53 KB (gzipped)
- **Runtime dependencies:** None (React is build-time only)
- **Deployment:** Automatic via GitHub Pages on push to `main`

**Daemon (Photobox server):**
- **Language:** Python 3.11+
- **Framework:** FastAPI
- **Camera:** V4L2 (libgphoto2 support for DSLR)
- **Distribution:** Wheel package via `pip install`
- **Systemd services:** photobox.service, photobox-first-boot.service, photobox-regulatory-domain.service

**Image build:**
- **Tool:** pi-gen (official Raspberry Pi builder)
- **Language:** Bash scripts
- **CI:** GitHub Actions on ARM runner
- **Output:** Compressed `.img.xz` with SHA256 checksums
- **Retention:** 30 days for CI artifacts; release-image cleanup keeps the two newest releases and gives older releases a seven-day grace period

## See Also

- [DESIGN.md](DESIGN.md) - Comprehensive architecture and rationale
- [installer/README.md](installer/README.md) - Web installer developer guide
- [docs/first-boot-and-pairing.md](docs/first-boot-and-pairing.md) - End-user setup walkthrough
- [docs/hardware-validation-m2.md](docs/hardware-validation-m2.md) - Hardware testing checklist
