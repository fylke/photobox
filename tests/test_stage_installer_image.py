import hashlib
import json

import pytest

from tools.stage_installer_image import stage_image


def test_stages_verified_image_and_capabilities(tmp_path):
    release = tmp_path / "release"
    release.mkdir()
    image = release / "photobox.img.xz"
    image.write_bytes(b"compressed image")
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    (release / "SHA256SUMS").write_text(f"{digest}  {image.name}\n")
    (release / "photobox-image-capabilities.json").write_text('{"boot_debug": true}\n')
    destination = tmp_path / "pages"
    stage_image(release, destination)
    assert (destination / "base.img.xz").read_bytes() == image.read_bytes()
    assert json.loads((destination / "manifest.json").read_text()) == {
        "sha256": digest,
        "size": len(image.read_bytes()),
        "bootDebug": True,
    }


def test_rejects_bad_checksum_before_staging(tmp_path):
    image = tmp_path / "photobox.img.xz"
    image.write_bytes(b"image")
    (tmp_path / "SHA256SUMS").write_text(f"{'0' * 64}  {image.name}\n")
    with pytest.raises(ValueError, match="checksum mismatch"):
        stage_image(tmp_path, tmp_path / "pages")
    assert not (tmp_path / "pages").exists()


def test_legacy_release_does_not_claim_boot_debug_support(tmp_path):
    image = tmp_path / "photobox.img.xz"
    image.write_bytes(b"image")
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    (tmp_path / "SHA256SUMS").write_text(f"{digest}  {image.name}\n")
    stage_image(tmp_path, tmp_path / "pages")
    manifest = json.loads((tmp_path / "pages/manifest.json").read_text())
    assert manifest["bootDebug"] is False
