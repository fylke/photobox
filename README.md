# Photobox

Photobox is a local photo-booth daemon with a browser-based capture screen.

## Run

Install the package and start the service:

```sh
python -m pip install .
photobox
```

Open `http://localhost:8000` on the booth screen. By default, the daemon captures from `/dev/video0` using the system `ffmpeg` executable. Install `ffmpeg` on the host and connect a V4L2-compatible webcam before starting the service.

For development without a camera, run with the mock driver:

```sh
PHOTOBOX_CAMERA=mock photobox
```

## Configuration

- `PHOTOBOX_CAMERA`: `webcam` (default) or `mock`.
- `PHOTOBOX_CAMERA_DEVICE`: V4L2 device path; defaults to `/dev/video0`.
- `PHOTOBOX_DATA_DIR`: photo and session storage directory; defaults to `~/photobox`.
- `PHOTOBOX_HOST`: bind address; defaults to `0.0.0.0`.
- `PHOTOBOX_PORT`: HTTP port; defaults to `8000`.