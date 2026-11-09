import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main(executable: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="photobox-smoke-") as temporary_dir:
        directory = Path(temporary_dir)
        tool = directory / executable.name
        shutil.copy2(executable, tool)
        image = directory / "photobox-test.img.xz"
        image.write_bytes(b"test image")
        (directory / "SHA256SUMS").write_text(
            f"{hashlib.sha256(image.read_bytes()).hexdigest()}  {image.name}\n"
            f"{hashlib.sha256(tool.read_bytes()).hexdigest()}  {tool.name}\n",
            encoding="utf-8",
        )
        output = directory / "device"
        command = [str(tool), "--wifi-country", "US", "--output-dir", str(output)]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode or not (output / "photobox-device.json").is_file():
            raise RuntimeError(f"Standalone provisioner failed: {result.stderr}")
        if "SHA-256" in result.stdout:
            raise RuntimeError("Successful checksum verification must be silent")

        image.write_bytes(b"corrupt image")
        bad_output = directory / "bad-device"
        command[-1] = str(bad_output)
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode == 0 or bad_output.exists():
            raise RuntimeError("Standalone provisioner accepted a corrupt image")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())