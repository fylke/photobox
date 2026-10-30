# Photobox

Photobox is a local photo-booth daemon with a browser-based capture screen.

## Run

Install the package and prepare the one-time setup PIN:

```sh
python -m pip install .
photobox-setup-pin
```

The setup command prints a random 10-digit PIN once and stores only its hash in the configured data directory. Keep the PIN private; the first successful admin claim consumes it. This initializes an already-installed host. It does not build a per-device OS image or configure Wi-Fi.

To prepare a private per-device credential bundle:

```sh
photobox-provision --output-dir "$HOME/photobox-device-setup"
```

This prints the device’s SSID, Wi-Fi password, and setup PIN once; it writes `device.json` and a Wi-Fi join QR. On Linux, the output directory and files are restricted to the owner. **Without `--base-image`, it does not create or modify a bootable image, configure a hotspot, or connect a Pi to Wi-Fi yet.** Keep the output directory private and out of Git/shared CI artifacts.

To put the credentials into a generic Raspberry Pi OS Lite image built by CI, run the provisioner on Linux:

```sh
photobox-provision --base-image photobox.img.xz --wifi-country GB \
  --output-dir "$HOME/photobox-device-setup"
```

Replace `GB` with the two-letter ISO country code where the Pi will operate. The command writes `photobox-device.img` beside the private credential bundle. It requires `losetup`, `lsblk`, `udevadm`, `mount`, and `install`; it may prompt for `sudo` to update the image. The image contains the PIN hash, a NetworkManager setup hotspot profile, and Wi-Fi settings, not the setup PIN.

On the provisioned image, the admin page can connect the Pi to venue WPA-Personal Wi-Fi. NetworkManager retains the setup hotspot if connection fails, and automatically retries a saved venue connection after reboot. The daemon uses NetworkManager D-Bus with a PolicyKit rule limited to network control and system connection changes; credentials are not passed as command-line arguments. These network flows still need physical Pi validation.

You can still use the bundle’s setup-PIN hash on an already-installed host by setting `PHOTOBOX_DEVICE_CONFIG` to the private `device.json` path when starting `photobox`. The daemon validates that the file is owner-only and uses its PIN hash for first-admin claim. Live Wi-Fi management is only enabled on the provisioned Pi image.

Start the service:

```sh
photobox
```

Open `http://localhost:8000` from a browser that can reach the host and enter the setup PIN. By default, the daemon captures from `/dev/video0` using the system `ffmpeg` executable. Install `ffmpeg` on the host and connect a V4L2-compatible webcam before starting the service.

For development without a camera, run with the mock driver:

```sh
PHOTOBOX_CAMERA=mock photobox
```

The pairing PIN must still be initialized with `photobox-setup-pin` first. The Pi hotspot and NetworkManager integration require the provisioned Pi image; on a development host, the phone or laptop must already be on a network that can reach the daemon.

## Configuration

- `PHOTOBOX_CAMERA`: `webcam` (default) or `mock`.
- `PHOTOBOX_CAMERA_DEVICE`: V4L2 device path; defaults to `/dev/video0`.
- `PHOTOBOX_DATA_DIR`: photo and session storage directory; defaults to `~/photobox`.
- `PHOTOBOX_HOST`: bind address; defaults to `0.0.0.0`.
- `PHOTOBOX_PORT`: HTTP port; defaults to `8000`.