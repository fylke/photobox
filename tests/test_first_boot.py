import stat

from photobox import first_boot
from photobox.pairing import PairingManager, hash_setup_pin


def test_bootstrap_profile_requires_imager_country_and_unconfigured_device(tmp_path, monkeypatch):
    monkeypatch.setattr(first_boot.os, "fchown", lambda descriptor, owner, group: None)
    command_line = "quiet cfg80211.ieee80211_regdom=GB rootwait"
    assert not first_boot.install_bootstrap_profile(tmp_path, "quiet rootwait")
    assert not first_boot.install_bootstrap_profile(
        tmp_path, "cfg80211.ieee80211_regdom=GB cfg80211.ieee80211_regdom=US"
    )
    assert first_boot.install_bootstrap_profile(tmp_path, command_line)
    profile = tmp_path / "run/NetworkManager/system-connections/photobox-first-boot.nmconnection"
    assert "ssid=Photobox Setup" in profile.read_text()
    assert "wifi-security" not in profile.read_text()
    assert stat.S_IMODE(profile.stat().st_mode) == 0o600
    assert first_boot.install_bootstrap_profile(tmp_path, "quiet rootwait")

    PairingManager(tmp_path / "var/lib/photobox/pairing.sqlite3", hash_setup_pin("123456"))
    assert not first_boot.install_bootstrap_profile(tmp_path, command_line)


def test_bootstrap_profile_fails_closed_for_invalid_existing_database(tmp_path, monkeypatch):
    monkeypatch.setattr(first_boot.os, "fchown", lambda descriptor, owner, group: None)
    database = tmp_path / "var/lib/photobox/pairing.sqlite3"
    database.parent.mkdir(parents=True)
    database.write_text("invalid database", encoding="ascii")
    assert not first_boot.install_bootstrap_profile(
        tmp_path, "cfg80211.ieee80211_regdom=GB"
    )
