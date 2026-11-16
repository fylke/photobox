import shutil
import subprocess
from pathlib import Path

LOG_DIRECTORY = Path("/boot/firmware/photobox-debug")
MAX_FILE_BYTES = 50 * 1024 * 1024
FILE_COUNT = 4
MIN_FREE_BYTES = 64 * 1024 * 1024


class BootLog:
    def __init__(
        self,
        directory: Path,
        max_file_bytes: int = MAX_FILE_BYTES,
        file_count: int = FILE_COUNT,
        min_free_bytes: int = MIN_FREE_BYTES,
    ) -> None:
        self.directory = directory
        self.max_file_bytes = max_file_bytes
        self.file_count = file_count
        self.min_free_bytes = min_free_bytes
        directory.mkdir(parents=True, exist_ok=True)
        for index in range(file_count):
            path = self._path(index)
            if path.exists() and path.stat().st_size > max_file_bytes:
                raise ValueError(f"Boot debug log exceeds its size limit: {path}")

    def _path(self, index: int) -> Path:
        return self.directory / ("boot.log" if index == 0 else f"boot.log.{index}")

    def _rotate(self) -> None:
        for index in range(self.file_count - 1, 0, -1):
            source = self._path(index - 1)
            if source.exists():
                source.replace(self._path(index))

    def write(self, data: bytes) -> None:
        while data:
            path = self._path(0)
            size = path.stat().st_size if path.exists() else 0
            if size >= self.max_file_bytes:
                self._rotate()
                size = 0
            chunk = data[: self.max_file_bytes - size]
            if shutil.disk_usage(self.directory).free - len(chunk) < self.min_free_bytes:
                raise OSError("Insufficient free space on the boot partition for debug logs")
            with path.open("ab") as output:
                output.write(chunk)
            data = data[len(chunk) :]


def main() -> None:
    log = BootLog(LOG_DIRECTORY)
    process = subprocess.Popen(
        ["journalctl", "--boot=0", "--follow", "--no-pager", "--output=short-precise"],
        stdout=subprocess.PIPE,
    )
    try:
        assert process.stdout is not None
        while chunk := process.stdout.read1(65536):
            log.write(chunk)
        raise RuntimeError(f"journalctl stopped unexpectedly with exit code {process.wait()}")
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait()
        if process.stdout is not None:
            process.stdout.close()


if __name__ == "__main__":
    main()
