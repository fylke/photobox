import argparse
import hashlib
import json
import shutil
from pathlib import Path


def stage_image(release_dir: Path, destination: Path) -> None:
    images = list(release_dir.glob("*.img.xz"))
    if len(images) != 1:
        raise ValueError(f"Expected exactly one image, found {len(images)}")
    image = images[0]
    checksum_lines = (release_dir / "SHA256SUMS").read_text(encoding="ascii").splitlines()
    expected = [
        line[:64]
        for line in checksum_lines
        if len(line) > 66 and line[64:66] in ("  ", " *") and line[66:] == image.name
    ]
    if len(expected) != 1 or len(expected[0]) != 64:
        raise ValueError("Expected exactly one checksum for the image")
    digest = hashlib.sha256()
    with image.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected[0]:
        raise ValueError("Image checksum mismatch")

    capabilities_path = release_dir / "photobox-image-capabilities.json"
    boot_debug = False
    if capabilities_path.exists():
        capabilities = json.loads(capabilities_path.read_text(encoding="utf-8"))
        if not isinstance(capabilities.get("boot_debug"), bool):
            raise ValueError("Invalid image capabilities")
        boot_debug = capabilities["boot_debug"]
    else:
        print("Release has no boot-debug capability metadata; debug will be unavailable.")

    destination.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(image, destination / "base.img.xz")
    (destination / "manifest.json").write_text(
        json.dumps(
            {
                "sha256": digest.hexdigest(),
                "size": image.stat().st_size,
                "bootDebug": boot_debug,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage a verified image for the web installer.")
    parser.add_argument("release_dir", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    stage_image(args.release_dir, args.destination)
