import re
import sqlite3

import pytest

from photobox.pairing import PairingManager, hash_setup_pin
from photobox.provision import main


def test_local_setup_command_prints_pin_once_and_stores_only_hash(
    monkeypatch,
    tmp_path,
    capsys,
):
    monkeypatch.setenv("PHOTOBOX_DATA_DIR", str(tmp_path))

    main()

    output = capsys.readouterr().out
    match = re.search(r"PIN: ([0-9]{10})", output)
    assert match is not None
    pin = match.group(1)

    with sqlite3.connect(tmp_path / "pairing.sqlite3") as connection:
        stored_values = " ".join(
            str(value)
            for row in connection.execute("SELECT value FROM settings")
            for value in row
        )
    assert pin not in stored_values

    pairing = PairingManager(tmp_path / "pairing.sqlite3", None)
    credential = pairing.claim_admin(pin)
    assert pairing.authenticate(credential.token).role == "admin"

    with pytest.raises(SystemExit):
        main()
    assert "already been initialized" in capsys.readouterr().err


def test_local_setup_command_refuses_to_replace_existing_pin(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("PHOTOBOX_DATA_DIR", str(tmp_path))
    PairingManager(tmp_path / "pairing.sqlite3", hash_setup_pin("1234567890"))

    with pytest.raises(SystemExit):
        main()

    assert "already been initialized" in capsys.readouterr().err
