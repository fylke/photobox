import os

import uvicorn


def run() -> None:
    uvicorn.run(
        "photobox.api:app",
        host=os.environ.get("PHOTOBOX_HOST", "0.0.0.0"),
        port=int(os.environ.get("PHOTOBOX_PORT", "8000")),
    )