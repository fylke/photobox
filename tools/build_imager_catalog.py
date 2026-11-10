import argparse
import hashlib
import json
import lzma
from datetime import date
from pathlib import Path
from urllib.parse import quote


def build_catalog(image: Path, repository: str, tag: str) -> dict[str, object]:
    compressed_hash = hashlib.sha256()
    with image.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            compressed_hash.update(chunk)
    image_hash = hashlib.sha256()
    image_size = 0
    with lzma.open(image, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            image_hash.update(chunk)
            image_size += len(chunk)
    if not image_size or image_size % 512:
        raise ValueError("The uncompressed image must contain complete 512-byte sectors")
    url = (
        f"https://github.com/{repository}/releases/download/"
        f"{quote(tag, safe='')}/{quote(image.name, safe='')}"
    )
    return {
        "imager": {
            "devices": [
                {"name": "Raspberry Pi 5", "tags": ["pi5-64bit"], "matching_type": "inclusive"},
                {"name": "Raspberry Pi 4", "tags": ["pi4-64bit"], "matching_type": "inclusive"},
                {"name": "No filtering", "tags": [], "matching_type": "inclusive"},
            ]
        },
        "os_list": [{
            "name": f"Photobox {tag}",
            "description": "Photobox for Raspberry Pi 4 and 5 (hardware testing prerelease)",
            "url": url,
            "extract_size": image_size,
            "extract_sha256": image_hash.hexdigest(),
            "image_download_size": image.stat().st_size,
            "image_download_sha256": compressed_hash.hexdigest(),
            "release_date": date.today().isoformat(),
            "init_format": "systemd",
            "devices": ["pi4-64bit", "pi5-64bit"],
            "capabilities": [],
        }],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Raspberry Pi Imager catalogue.")
    parser.add_argument("image", type=Path)
    parser.add_argument("repository")
    parser.add_argument("tag")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    catalog = build_catalog(args.image, args.repository, args.tag)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()