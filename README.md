# Photobox

Photobox is a local photo-booth daemon with a browser-based capture screen.

## Choose a setup path

- **Try Photobox on this computer:** install it, initialize a local setup PIN, and start the daemon. The computer and phone must already share a network. This does not configure a Pi hotspot.
- **Set up a Raspberry Pi:** use Raspberry Pi Imager and the first-boot setup network. This is the only supported Pi setup flow. Follow [First Boot and Pairing](docs/first-boot-and-pairing.md) for the walkthrough. Physical hardware validation is still required.

## Run on this computer

Use Python 3.11 or newer. From the project directory, install Photobox and initialize its one-time administrator PIN:

```sh
python3 -m pip install .
photobox-setup-pin
```

Record the 6-digit PIN when it is printed; it is shown only once. The command stores a hash under `PHOTOBOX_DATA_DIR` (default: `~/photobox`) and refuses to initialize a data directory that already has a PIN. If you set a custom `PHOTOBOX_DATA_DIR`, use the same value for both the setup command and daemon.

Connect a V4L2-compatible webcam and install the system `ffmpeg` executable for camera capture, or run without a camera using the mock driver:

```sh
photobox
# Or, without a camera:
PHOTOBOX_CAMERA=mock photobox
```

Open `http://localhost:8000` on the same computer, or use the computer's reachable network address from another device. Enter the setup PIN to claim administrator access. The local-host path does not create a Wi-Fi hotspot or manage Wi-Fi; the phone or laptop must already be on a network that can reach the computer.

## Raspberry Pi image

Each prerelease publishes an Imager catalogue to GitHub Pages and the matching image as a GitHub Release asset. Set the repository's Pages source to **GitHub Actions** before publishing. Users select the Wi-Fi country in Imager's **Localisation** step; see [First Boot and Pairing](docs/first-boot-and-pairing.md#set-up-with-raspberry-pi-imager). The catalogue and first-boot hotspot have not yet been validated on physical hardware.

On the Pi, the first-boot setup network is open and temporary. The administrator claims the booth and switches it to a private WPA-Personal hotspot, then may configure venue Wi-Fi. Enterprise Wi-Fi and captive portals are not supported. Local capture does not require internet access.

For generic DSLR still capture through libgphoto2, set the camera to capture JPEG and set `PHOTOBOX_CAMERA=gphoto2`. The app uses the configured V4L2 webcam for preview and as a capture fallback when available. This initial adapter does not claim DSLR live preview. Exact camera-model compatibility has not been physically validated.

The public `/api/cameras` status endpoint reports registered camera IDs, assigned preview/capture roles, capabilities, and current availability. If no capture camera is available, the booth remains up for setup but refuses to start a photo session.

## Configuration

- `PHOTOBOX_CAMERA`: `webcam` (default), `gphoto2`, or `mock`.
- `PHOTOBOX_CAMERA_DEVICE`: V4L2 device path; defaults to `/dev/video0`.
- `PHOTOBOX_GPHOTO2_PORT`: optional gphoto2 port selector when multiple cameras are attached.
- `PHOTOBOX_DATA_DIR`: photo and session storage directory; defaults to `~/photobox`.
- `PHOTOBOX_HOST`: bind address; defaults to `0.0.0.0`.
- `PHOTOBOX_PORT`: HTTP port; defaults to `8000`.