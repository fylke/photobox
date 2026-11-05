# Photobox

Photobox is a local photo-booth daemon with a browser-based capture screen.

## Choose a setup path

- **Try Photobox on this computer:** install it, initialize a local setup PIN, and start the daemon. The computer and phone must already share a network. This does not configure a Pi hotspot.
- **Set up a Raspberry Pi:** download the generic image, create a private image for that Pi on a Linux computer, then flash it to a microSD card. Follow [First Boot and Pairing](docs/first-boot-and-pairing.md) for the full walkthrough.

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

The generic Raspberry Pi OS image is built by the `Build Raspberry Pi image` GitHub Actions workflow. Download its `photobox-raspios-arm64` artifact from a workflow run, or use the `.img.xz` and `SHA256SUMS` assets attached to an alpha, beta, or release-candidate prerelease. Verify the checksum before provisioning. The generic image has no per-device Wi-Fi password or setup PIN; provisioning creates those locally and inserts only the PIN hash into the image.

Provisioning requires Linux, the project installed on the provisioning computer, and the image tools `losetup`, `lsblk`, `udevadm`, `mount`, and `install`. See the linked first-boot guide for the full commands, required country code, SD-card flashing, and first administrator claim. Do not share the per-device image or credential bundle: they contain that Pi's Wi-Fi credentials.

On the provisioned Pi, an administrator can configure WPA-Personal venue Wi-Fi from the admin page. If connection fails, the setup hotspot remains available; a saved venue connection is retried after reboot. Enterprise Wi-Fi and captive-portal sign-in are not supported. These image and network paths still need physical Pi validation.

An installed host can also use the setup-PIN hash from a private provisioning bundle by setting `PHOTOBOX_DEVICE_CONFIG` to its `device.json` path when starting Photobox. The file must remain owner-only. This does not enable hotspot or live Wi-Fi management on that host.

For generic DSLR still capture through libgphoto2, set the camera to capture JPEG and set `PHOTOBOX_CAMERA=gphoto2`. The app uses the configured V4L2 webcam for preview and as a capture fallback when available. This initial adapter does not claim DSLR live preview. Exact camera-model compatibility has not been physically validated.

The public `/api/cameras` status endpoint reports registered camera IDs, assigned preview/capture roles, capabilities, and current availability. If no capture camera is available, the booth remains up for setup but refuses to start a photo session.

## Configuration

- `PHOTOBOX_CAMERA`: `webcam` (default), `gphoto2`, or `mock`.
- `PHOTOBOX_CAMERA_DEVICE`: V4L2 device path; defaults to `/dev/video0`.
- `PHOTOBOX_GPHOTO2_PORT`: optional gphoto2 port selector when multiple cameras are attached.
- `PHOTOBOX_DATA_DIR`: photo and session storage directory; defaults to `~/photobox`.
- `PHOTOBOX_HOST`: bind address; defaults to `0.0.0.0`.
- `PHOTOBOX_PORT`: HTTP port; defaults to `8000`.