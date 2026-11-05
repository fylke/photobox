import subprocess
import sys
import zipfile
from pathlib import Path

import qrcode


def test_standalone_provisioner_runs_without_installed_python_packages(tmp_path):
    project_root = Path(__file__).parents[1]
    qrcode_package = Path(qrcode.__file__).parent
    bundle_path = tmp_path / "photobox-provision.pyz"
    output_dir = tmp_path / "device"
    subprocess.run(
        [
            sys.executable,
            str(project_root / "tools" / "build_provisioner.py"),
            "--qrcode-package",
            str(qrcode_package),
            "--output",
            str(bundle_path),
        ],
        check=True,
    )
    with zipfile.ZipFile(bundle_path) as bundle:
        assert "licenses/qrcode-LICENSE" in bundle.namelist()

    result = subprocess.run(
        [sys.executable, "-S", str(bundle_path), "--output-dir", str(output_dir)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "No bootable image was created" in result.stdout
    assert (output_dir / "device.json").is_file()
    assert (output_dir / "wifi-join.svg").is_file()