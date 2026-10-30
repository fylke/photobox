# Photobox

Photobox is a local photo-booth daemon with a browser-based capture screen.

## Run

Install the package and prepare the one-time setup PIN:

```sh
python -m pip install .
photobox-setup-pin
```

The setup command prints a random 10-digit PIN once and stores only its hash in the configured data directory. Keep the PIN private; the first successful admin claim consumes it. This initializes an already-installed host. It does not build a per-device OS image or configure Wi-Fi.

Start the service:

```sh
photobox
```

Open `http://localhost:8000` from a browser that can reach the host and enter the setup PIN. By default, the daemon captures from `/dev/video0` using the system `ffmpeg` executable. Install `ffmpeg` on the host and connect a V4L2-compatible webcam before starting the service.

For development without a camera, run with the mock driver:

```sh
PHOTOBOX_CAMERA=mock photobox
```

The pairing PIN must still be initialized with `photobox-setup-pin` first. The Pi hotspot, Wi-Fi provisioning, and automatic network setup are not implemented yet; the phone or laptop must already be on a network that can reach the daemon.

## Configuration

- `PHOTOBOX_CAMERA`: `webcam` (default) or `mock`.
- `PHOTOBOX_CAMERA_DEVICE`: V4L2 device path; defaults to `/dev/video0`.
- `PHOTOBOX_DATA_DIR`: photo and session storage directory; defaults to `~/photobox`.
- `PHOTOBOX_HOST`: bind address; defaults to `0.0.0.0`.
- `PHOTOBOX_PORT`: HTTP port; defaults to `8000`.