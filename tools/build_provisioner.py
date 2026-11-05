import argparse
import shutil
import tempfile
import zipapp
from pathlib import Path


def build(qrcode_package: Path, output: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    source_package = project_root / "src" / "photobox"
    if not (qrcode_package / "__init__.py").is_file():
        raise ValueError(f"Not a qrcode package directory: {qrcode_package}")
    license_files = sorted(
        path
        for dist_info in qrcode_package.parent.glob("qrcode-*.dist-info")
        for path in (*dist_info.glob("LICENSE*"), *(dist_info / "licenses").glob("LICENSE*"))
        if path.is_file()
    )
    if not license_files:
        raise ValueError("Could not find the qrcode package license")

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="photobox-provision-") as temporary_dir:
        app_dir = Path(temporary_dir)
        app_package = app_dir / "photobox"
        app_package.mkdir()
        for module in ("__init__.py", "pairing.py", "provision.py"):
            shutil.copyfile(source_package / module, app_package / module)

        shutil.copytree(
            qrcode_package,
            app_dir / "qrcode",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        license_dir = app_dir / "licenses"
        license_dir.mkdir()
        shutil.copyfile(license_files[0], license_dir / "qrcode-LICENSE")
        (app_dir / "__main__.py").write_text(
            "from photobox.provision import provision_device\n\n"
            "if __name__ == '__main__':\n"
            "    provision_device()\n",
            encoding="utf-8",
        )
        zipapp.create_archive(
            app_dir,
            target=output,
            interpreter="/usr/bin/env python3",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the standalone Photobox provisioner.")
    parser.add_argument("--qrcode-package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    build(arguments.qrcode_package, arguments.output)


if __name__ == "__main__":
    main()