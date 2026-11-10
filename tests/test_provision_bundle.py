import hashlib
import lzma

import pytest

from tools.build_imager_catalog import build_catalog


def test_imager_catalog_contains_image_metadata(tmp_path):
    content = b"image" * 512
    image = tmp_path / "photobox.img.xz"
    image.write_bytes(lzma.compress(content))
    catalog = build_catalog(image, "example/photobox", "v1.0-beta1")
    entry = catalog["os_list"][0]
    assert entry["url"] == (
        "https://github.com/example/photobox/releases/download/v1.0-beta1/photobox.img.xz"
    )
    assert entry["extract_size"] == len(content)
    assert entry["extract_sha256"] == hashlib.sha256(content).hexdigest()
    assert entry["image_download_sha256"] == hashlib.sha256(image.read_bytes()).hexdigest()
    assert entry["init_format"] == "systemd"


def test_imager_catalog_rejects_incomplete_image(tmp_path):
    image = tmp_path / "photobox.img.xz"
    image.write_bytes(lzma.compress(b"incomplete"))
    with pytest.raises(ValueError, match="complete 512-byte sectors"):
        build_catalog(image, "example/photobox", "v1")
