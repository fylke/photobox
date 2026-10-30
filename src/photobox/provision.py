import os
import sys
from pathlib import Path

from photobox.pairing import PairingError, PairingManager, generate_setup_pin, hash_setup_pin


def main() -> None:
    data_dir = Path(os.environ.get("PHOTOBOX_DATA_DIR", "~/photobox")).expanduser()
    pairing = PairingManager(data_dir / "pairing.sqlite3", None)
    if pairing.status()["configured"]:
        print("Photobox setup has already been initialized; refusing to replace the PIN.", file=sys.stderr)
        raise SystemExit(1)

    pin = generate_setup_pin()
    try:
        pairing.provision_setup_pin(hash_setup_pin(pin))
    except PairingError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error

    print("One-time Photobox setup PIN (record it now; it will not be shown again):")
    print(f"PIN: {pin}")
    print("This command stores only a hash. The PIN is consumed when the first admin claims the booth.")


if __name__ == "__main__":
    main()