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

Each prerelease publishes a Photobox image as a GitHub Release asset and publishes the web installer to GitHub Pages. The web installer is the recommended way to write images to your SD card.

**To set up a Photobox booth:**
1. Open the [Photobox Web Installer](https://fylke.github.io/photobox/installer)
2. Select your Raspberry Pi model (4 or 5)
3. Select your Wi-Fi country
4. Connect your SD card reader and write the image
5. Insert the card into your Pi, connect the camera, and power on

The image includes Photobox and is pre-configured for the first-boot setup network. Users select the Wi-Fi country during write time; see [First Boot and Pairing](docs/first-boot-and-pairing.md) for the full setup walkthrough. The first-boot hotspot and web installer have not yet been validated on physical hardware.

For generic DSLR still capture through libgphoto2, set the camera to capture JPEG and set `PHOTOBOX_CAMERA=gphoto2`. The app uses the configured V4L2 webcam for preview and as a capture fallback when available. This initial adapter does not claim DSLR live preview. Exact camera-model compatibility has not been physically validated.

The public `/api/cameras` status endpoint reports registered camera IDs, assigned preview/capture roles, capabilities, and current availability. If no capture camera is available, the booth remains up for setup but refuses to start a photo session.

## Configuration

- `PHOTOBOX_CAMERA`: `webcam` (default), `gphoto2`, or `mock`.
- `PHOTOBOX_CAMERA_DEVICE`: V4L2 device path; defaults to `/dev/video0`.
- `PHOTOBOX_GPHOTO2_PORT`: optional gphoto2 port selector when multiple cameras are attached.
- `PHOTOBOX_DATA_DIR`: photo and session storage directory; defaults to `~/photobox`.
- `PHOTOBOX_HOST`: bind address; defaults to `0.0.0.0`.
- `PHOTOBOX_PORT`: HTTP port; defaults to `8000`.