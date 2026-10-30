import hashlib
import hmac
import secrets
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

_PIN_LENGTH = 10
_SCRYPT_N = 1 << 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_TOKEN_BYTES = 32
_DEFAULT_INVITATION_TTL = 10 * 60
_DEFAULT_GUEST_TTL = 12 * 60 * 60
_MAX_INVITATION_TTL = 60 * 60
_CLAIM_FAILURE_LIMIT = 5
_CLAIM_WINDOW_SECONDS = 15 * 60
_CLAIM_LOCKOUT_SECONDS = 5 * 60


class PairingError(Exception):
    """A pairing, credential, or authorization operation was rejected."""


class PairingRateLimited(PairingError):
    """A setup PIN source has exceeded the allowed number of attempts."""


@dataclass(frozen=True)
class IssuedCredential:
    token: str
    credential_id: str
    role: str
    expires_at: int | None


@dataclass(frozen=True)
class Principal:
    credential_id: str
    role: str
    expires_at: int | None


def generate_setup_pin() -> str:
    return f"{secrets.randbelow(10**_PIN_LENGTH):0{_PIN_LENGTH}d}"


def hash_setup_pin(pin: str) -> str:
    if not _is_setup_pin(pin):
        raise ValueError("Setup PIN must contain exactly 10 digits")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        pin.encode("ascii"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=32,
    )
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_setup_pin(pin: str, encoded_hash: str) -> bool:
    if not _is_setup_pin(pin):
        return False
    try:
        algorithm, salt_hex, digest_hex = encoded_hash.split("$", maxsplit=2)
        if algorithm != "scrypt":
            return False
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.scrypt(
            pin.encode("ascii"),
            salt=bytes.fromhex(salt_hex),
            n=_SCRYPT_N,
            r=_SCRYPT_R,
            p=_SCRYPT_P,
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def _is_setup_pin(pin: str) -> bool:
    return len(pin) == _PIN_LENGTH and pin.isascii() and pin.isdigit()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class PairingManager:
    def __init__(
        self,
        database_path: Path,
        setup_pin_hash: str | None,
        clock: Callable[[], int] = lambda: int(time.time()),
        guest_ttl_seconds: int = _DEFAULT_GUEST_TTL,
    ):
        self.database_path = Path(database_path)
        self.clock = clock
        if guest_ttl_seconds < 1:
            raise ValueError("guest_ttl_seconds must be positive")
        self.guest_ttl_seconds = guest_ttl_seconds
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize(setup_pin_hash)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self, setup_pin_hash: str | None) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS credentials (
                    credential_id TEXT PRIMARY KEY,
                    token_hash TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL CHECK (role IN ('admin', 'guest')),
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER,
                    revoked_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS invitations (
                    invitation_id TEXT PRIMARY KEY,
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    created_by TEXT NOT NULL,
                    redeemed_at INTEGER,
                    revoked_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS claim_attempts (
                    client_key_hash TEXT PRIMARY KEY,
                    window_started_at INTEGER NOT NULL,
                    failure_count INTEGER NOT NULL,
                    locked_until INTEGER NOT NULL
                );
                """
            )
            if setup_pin_hash is not None:
                initialized = connection.execute(
                    "SELECT value FROM settings WHERE key = 'setup_initialized'"
                ).fetchone()
                if initialized is None:
                    connection.execute(
                        "INSERT INTO settings (key, value) VALUES ('setup_initialized', '1')"
                    )
                    connection.execute(
                        "INSERT INTO settings (key, value) VALUES ('setup_pin_hash', ?)",
                        (setup_pin_hash,),
                    )

    def status(self) -> dict[str, bool]:
        with self._connect() as connection:
            initialized = connection.execute(
                "SELECT value FROM settings WHERE key = 'setup_initialized'"
            ).fetchone()
            setup_pin = connection.execute(
                "SELECT value FROM settings WHERE key = 'setup_pin_hash'"
            ).fetchone()
        return {
            "configured": initialized is not None,
            "claimed": initialized is not None and setup_pin is None,
        }

    def provision_setup_pin(self, encoded_hash: str) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            initialized = connection.execute(
                "SELECT value FROM settings WHERE key = 'setup_initialized'"
            ).fetchone()
            if initialized is not None:
                raise PairingError("Setup has already been initialized")
            connection.execute(
                "INSERT INTO settings (key, value) VALUES ('setup_initialized', '1')"
            )
            connection.execute(
                "INSERT INTO settings (key, value) VALUES ('setup_pin_hash', ?)",
                (encoded_hash,),
            )

    def claim_admin(self, pin: str, client_key: str = "unknown") -> IssuedCredential:
        now = self.clock()
        key_hash = _token_hash(client_key)
        issued: IssuedCredential | None = None
        error: PairingError | None = None

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            attempt = connection.execute(
                "SELECT * FROM claim_attempts WHERE client_key_hash = ?", (key_hash,)
            ).fetchone()
            if attempt is not None and attempt["locked_until"] > now:
                raise PairingRateLimited("Setup claim rate limit exceeded; try again later")

            row = connection.execute(
                "SELECT value FROM settings WHERE key = 'setup_pin_hash'"
            ).fetchone()
            if row is None:
                raise PairingError("Setup PIN is unavailable or has already been used")

            if not verify_setup_pin(pin, row["value"]):
                self._record_claim_failure(connection, key_hash, attempt, now)
                error = PairingError("Invalid setup PIN")
            else:
                connection.execute("DELETE FROM settings WHERE key = 'setup_pin_hash'")
                connection.execute(
                    "DELETE FROM claim_attempts WHERE client_key_hash = ?", (key_hash,)
                )
                issued = self._insert_credential(connection, "admin", None, now)

        if error is not None:
            raise error
        if issued is None:
            raise PairingError("Could not claim this booth")
        return issued

    def _record_claim_failure(
        self,
        connection: sqlite3.Connection,
        key_hash: str,
        previous: sqlite3.Row | None,
        now: int,
    ) -> None:
        if previous is None or now - previous["window_started_at"] >= _CLAIM_WINDOW_SECONDS:
            window_started_at = now
            failure_count = 1
        else:
            window_started_at = previous["window_started_at"]
            failure_count = previous["failure_count"] + 1
        locked_until = (
            now + _CLAIM_LOCKOUT_SECONDS
            if failure_count >= _CLAIM_FAILURE_LIMIT
            else 0
        )
        connection.execute(
            """INSERT OR REPLACE INTO claim_attempts
               (client_key_hash, window_started_at, failure_count, locked_until)
               VALUES (?, ?, ?, ?)""",
            (key_hash, window_started_at, failure_count, locked_until),
        )

    def create_invitation(
        self,
        admin_token: str,
        ttl_seconds: int = _DEFAULT_INVITATION_TTL,
    ) -> str:
        if not 1 <= ttl_seconds <= _MAX_INVITATION_TTL:
            raise ValueError("Invitation lifetime must be between 1 second and 1 hour")
        now = self.clock()
        token = secrets.token_urlsafe(_TOKEN_BYTES)
        invitation_id = secrets.token_hex(16)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            admin = self._require_admin(connection, admin_token, now)
            connection.execute(
                """INSERT INTO invitations
                   (invitation_id, token_hash, created_at, expires_at, created_by)
                   VALUES (?, ?, ?, ?, ?)""",
                (invitation_id, _token_hash(token), now, now + ttl_seconds, admin.credential_id),
            )
        return token

    def redeem_invitation(self, invitation_token: str) -> IssuedCredential:
        now = self.clock()
        issued: IssuedCredential | None = None
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            invitation = connection.execute(
                """SELECT * FROM invitations
                   WHERE token_hash = ? AND redeemed_at IS NULL AND revoked_at IS NULL""",
                (_token_hash(invitation_token),),
            ).fetchone()
            if invitation is None or invitation["expires_at"] <= now:
                raise PairingError("Invitation is invalid, expired, or already used")

            connection.execute(
                "UPDATE invitations SET redeemed_at = ? WHERE invitation_id = ?",
                (now, invitation["invitation_id"]),
            )
            issued = self._insert_credential(
                connection, "guest", now + self.guest_ttl_seconds, now
            )
        return issued

    def authenticate(self, token: str) -> Principal:
        now = self.clock()
        with self._connect() as connection:
            row = connection.execute(
                """SELECT credential_id, role, expires_at, revoked_at FROM credentials
                   WHERE token_hash = ?""",
                (_token_hash(token),),
            ).fetchone()
        if (
            row is None
            or row["revoked_at"] is not None
            or (row["expires_at"] is not None and row["expires_at"] <= now)
        ):
            raise PairingError("Credential is invalid or expired")
        return Principal(row["credential_id"], row["role"], row["expires_at"])

    def revoke_credential(self, admin_token: str, credential_id: str) -> None:
        now = self.clock()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_admin(connection, admin_token, now)
            cursor = connection.execute(
                """UPDATE credentials SET revoked_at = ?
                   WHERE credential_id = ? AND role = 'guest' AND revoked_at IS NULL""",
                (now, credential_id),
            )
            if cursor.rowcount != 1:
                raise PairingError("Guest credential not found or already revoked")

    def list_guests(self, admin_token: str) -> list[dict[str, int | str | bool | None]]:
        now = self.clock()
        with self._connect() as connection:
            self._require_admin(connection, admin_token, now)
            rows = connection.execute(
                """SELECT credential_id, expires_at, revoked_at FROM credentials
                   WHERE role = 'guest' ORDER BY created_at, credential_id"""
            ).fetchall()
        return [
            {
                "credential_id": row["credential_id"],
                "expires_at": row["expires_at"],
                "revoked": row["revoked_at"] is not None,
            }
            for row in rows
        ]

    def _require_admin(
        self,
        connection: sqlite3.Connection,
        token: str,
        now: int,
    ) -> Principal:
        row = connection.execute(
            """SELECT credential_id, role, expires_at, revoked_at FROM credentials
               WHERE token_hash = ?""",
            (_token_hash(token),),
        ).fetchone()
        if (
            row is None
            or row["role"] != "admin"
            or row["revoked_at"] is not None
            or (row["expires_at"] is not None and row["expires_at"] <= now)
        ):
            raise PairingError("Administrator credential required")
        return Principal(row["credential_id"], row["role"], row["expires_at"])

    def _insert_credential(
        self,
        connection: sqlite3.Connection,
        role: str,
        expires_at: int | None,
        now: int,
    ) -> IssuedCredential:
        token = secrets.token_urlsafe(_TOKEN_BYTES)
        credential_id = secrets.token_hex(16)
        connection.execute(
            """INSERT INTO credentials
               (credential_id, token_hash, role, created_at, expires_at, revoked_at)
               VALUES (?, ?, ?, ?, ?, NULL)""",
            (credential_id, _token_hash(token), role, now, expires_at),
        )
        return IssuedCredential(token, credential_id, role, expires_at)
