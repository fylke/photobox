import tempfile
import unittest
from pathlib import Path

from photobox.pairing import (
    PairingError,
    PairingManager,
    generate_setup_pin,
    hash_setup_pin,
    verify_setup_pin,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_800_000_000

    def __call__(self) -> int:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += seconds


class PairingManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.directory = Path(self.temp_dir.name)
        self.pin = generate_setup_pin()
        self.pin_hash = hash_setup_pin(self.pin)
        self.manager = self.make_manager(self.directory)

    def make_manager(self, directory: Path) -> PairingManager:
        return PairingManager(
            directory / "pairing.sqlite3",
            self.pin_hash,
            clock=self.clock,
        )

    def test_setup_pin_is_random_ten_digit_and_scrypt_hashed(self):
        pin = generate_setup_pin()
        encoded_hash = hash_setup_pin(pin)

        self.assertRegex(pin, r"^[0-9]{10}$")
        self.assertTrue(verify_setup_pin(pin, encoded_hash))
        self.assertFalse(verify_setup_pin("0000000000", encoded_hash))
        self.assertTrue(encoded_hash.startswith("scrypt$"))

    def test_setup_pin_is_consumed_and_admin_survives_restart(self):
        admin = self.manager.claim_admin(self.pin)
        self.assertEqual(self.manager.authenticate(admin.token).role, "admin")

        restarted = self.make_manager(self.directory)
        self.assertEqual(restarted.authenticate(admin.token).role, "admin")
        with self.assertRaises(PairingError):
            restarted.claim_admin(self.pin)

        database_bytes = (self.directory / "pairing.sqlite3").read_bytes()
        self.assertNotIn(self.pin.encode(), database_bytes)
        self.assertNotIn(admin.token.encode(), database_bytes)

    def test_reopening_with_a_different_setup_pin_hash_is_rejected(self):
        PairingManager(self.directory / "pairing.sqlite3", self.pin_hash)

        with self.assertRaisesRegex(PairingError, "different setup PIN"):
            PairingManager(
                self.directory / "pairing.sqlite3",
                hash_setup_pin("1234567890"),
                clock=self.clock,
            )

    def test_invitation_is_one_use_and_guest_can_be_revoked(self):
        admin = self.manager.claim_admin(self.pin)
        invitation = self.manager.create_invitation(admin.token)
        guest = self.manager.redeem_invitation(invitation)

        self.assertEqual(self.manager.authenticate(guest.token).role, "guest")
        with self.assertRaises(PairingError):
            self.manager.redeem_invitation(invitation)

        self.manager.revoke_credential(admin.token, guest.credential_id)
        with self.assertRaises(PairingError):
            self.manager.authenticate(guest.token)

    def test_expired_invitation_cannot_be_redeemed(self):
        admin = self.manager.claim_admin(self.pin)
        invitation = self.manager.create_invitation(admin.token)
        self.clock.advance(601)

        with self.assertRaises(PairingError):
            self.manager.redeem_invitation(invitation)

    def test_setup_claim_attempts_are_rate_limited(self):
        for _ in range(5):
            with self.assertRaises(PairingError):
                self.manager.claim_admin("0000000000", client_key="phone-1")

        with self.assertRaisesRegex(PairingError, "rate limit"):
            self.manager.claim_admin(self.pin, client_key="phone-1")


if __name__ == "__main__":
    unittest.main()
