# Photobox

Photobox is a local photo-booth daemon with a browser-based capture screen.

## Set up Photobox

The recommended way to set up Photobox is on a **Raspberry Pi 4 or 5** with the included photo booth experience. Follow [First Boot and Pairing](docs/first-boot-and-pairing.md) for the walkthrough. Physical hardware validation is still in progress.

### Advanced: Run on this computer

For development or testing, you can run Photobox on any computer with Python 3.11 or newer:

```sh
python3 -m pip install .
photobox-setup-pin
```

Record the 6-digit PIN when it is printed; it is shown only once. Connect a V4L2-compatible webcam and install the system `ffmpeg` executable, or run with the mock driver:

```sh
photobox
# Or, without a camera:
PHOTOBOX_CAMERA=mock photobox
```

Open `http://localhost:8000`. The local-host path does not create a Wi-Fi hotspot; the phone must already be on a network that can reach the computer.

## Raspberry Pi image

Each prerelease publishes a Photobox image as a GitHub Release asset. The web installer prepares a configured image locally in your browser; Raspberry Pi Imager writes it to your SD card.

**To set up a Photobox booth:**
1. Open the [Photobox Web Installer](https://fylke.github.io/photobox/installer)
2. Select your Wi-Fi country and, optionally, boot debug
3. Prepare and save the image
4. Use Raspberry Pi Imager's **Use custom** option to write it to your SD card
5. Insert the card into your Pi, connect the camera, and power on

The image includes Photobox and is pre-configured for the first-boot setup network. See [First Boot and Pairing](docs/first-boot-and-pairing.md) for the full setup walkthrough. The first-boot hotspot and web installer have not yet been validated on physical hardware.

Maintainers can run the **Clean up old prerelease images** workflow manually from GitHub Actions. It keeps all assets on the most recently published prerelease and removes `.img.xz` and `SHA256SUMS` assets from older prereleases, leaving their releases, tags, and other assets intact. Old image download links will stop working. Cleanup refuses to run if the newest prerelease has no image; stable releases and draft releases are not changed. CI build artifacts have their own 30-day retention.

For generic DSLR still capture through libgphoto2, set the camera to capture JPEG and set `PHOTOBOX_CAMERA=gphoto2`. The app uses the configured V4L2 webcam for preview and as a capture fallback when available. This initial adapter does not claim DSLR live preview. Exact camera-model compatibility has not been physically validated.

The public `/api/cameras` status endpoint reports registered camera IDs, assigned preview/capture roles, capabilities, and current availability. If no capture camera is available, the booth remains up for setup but refuses to start a photo session.

## Configuration

- `PHOTOBOX_CAMERA`: `webcam` (default), `gphoto2`, or `mock`.
- `PHOTOBOX_CAMERA_DEVICE`: V4L2 device path; defaults to `/dev/video0`.
- `PHOTOBOX_GPHOTO2_PORT`: optional gphoto2 port selector when multiple cameras are attached.
- `PHOTOBOX_DATA_DIR`: photo and session storage directory; defaults to `~/photobox`.
- `PHOTOBOX_HOST`: bind address; defaults to `0.0.0.0`.
- `PHOTOBOX_PORT`: HTTP port; defaults to `8000`.