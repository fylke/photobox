# Key Design Decisions

This document captures architectural decisions for Photobox. For detailed design rationale, see [DESIGN.md](DESIGN.md).

## Web Installer

**Decision:** Provide a zero-installation web-based installer for writing Photobox images to SD cards.

**Why:**
- Users don't need to install Raspberry Pi Imager or any other software
- Works in any modern browser (Chrome, Edge, Brave)
- Single UI for all platforms (Windows, Mac, Linux)
- Direct WiFi country selection during write time
- Eliminates need for a custom Imager catalogue

**Platform:** React + TypeScript + Vite, compiled to static HTML/CSS/JS and deployed to GitHub Pages at https://fylke.github.io/photobox/installer

**Supported platforms:**
- Raspberry Pi 3 (armv7l)
- Raspberry Pi 4 (aarch64)
- Raspberry Pi 5 (aarch64)

**Supported countries:** 38 WiFi regulatory domains (set during image write; cannot be changed after first boot without reflashing)

**Deployment:**
- Source code: `installer/` at repository root
- Built artifacts: `docs/installer/` (deployed by GitHub Pages workflow)
- GitHub Actions workflow: `.github/workflows/pages.yml`

**Constraints:**
- Browser must support WebUSB (Chrome 61+, Edge 79+, Brave)
- No Firefox or Safari support (lack of WebUSB API)
- SD card reader must support USB mass storage (standard support)

## Raspberry Pi Image

**Decision:** Build minimal Pi OS images with Photobox preinstalled for Pi 3, 4, and 5.

**Why:**
- Single pre-configured image for reliable first-boot setup
- Users don't need to install Photobox manually
- Image build is deterministic and reproducible via CI

**Build process:**
- CI builds on ARM hardware (raspberry pi OS)
- Uses pi-gen (official Raspberry Pi OS builder) as base
- Custom stage adds Photobox services and configuration
- Output: compressed `.img.xz` file with SHA256 checksums

**First-boot behavior:**
- Opens temporary open WiFi network (`Photobox Setup`)
- Admin claims booth via web UI on `10.42.0.1:8000`
- Admin switches to private hotspot and configures venue WiFi (optional)
- Photobox daemon runs as systemd service

**WiFi regulatory domain:**
- Set at image write time by the web installer (not changeable after write)
- Prevents regulatory violations in different countries
- Embedded in OS image for reliability

## Setup and Pairing

**Decision:** All setup occurs via phone or local device; no cloud dependencies.

**Primary setup path:**
1. Write image with web installer (select WiFi country)
2. Boot Pi, connect to `Photobox Setup` network
3. Admin claims booth via `10.42.0.1:8000`
4. Switch to private hotspot and configure venue WiFi (optional)

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

**WiFi regulatory domains (38 countries):**
Supported by the web installer during image write. See `installer/src/config.ts` for full list.

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
- **Retention:** 30 days (pre-release artifacts)

## See Also

- [DESIGN.md](DESIGN.md) - Comprehensive architecture and rationale
- [installer/README.md](installer/README.md) - Web installer developer guide
- [docs/first-boot-and-pairing.md](docs/first-boot-and-pairing.md) - End-user setup walkthrough
- [docs/hardware-validation-m2.md](docs/hardware-validation-m2.md) - Hardware testing checklist
