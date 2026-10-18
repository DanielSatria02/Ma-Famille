"""Password hashing for customer accounts.

PBKDF2-HMAC-SHA256 from the standard library — no extra dependency, and
tuned to the same order of magnitude as the usual defaults so a stolen hash
is not cheap to crack.

Format: ``pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>``. Iterations
travel with the hash so raising the cost later does not invalidate accounts
already registered: each check reads the count it was made with.
"""

import hashlib
import hmac
import secrets

_ALGORITHM = "pbkdf2_sha256"
# ~600ms on the box this runs on; enough to make an offline crack expensive
# without making a login feel stuck.
_ITERATIONS = 600_000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _ITERATIONS
    ).hex()
    return f"{_ALGORITHM}${_ITERATIONS}${salt.hex()}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if algorithm != _ALGORITHM:
        return False
    try:
        iterations_count = int(iterations)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations_count
    )
    # Constant-time compare: a plain == would leak how much of the guess was
    # right through timing.
    return hmac.compare_digest(candidate, expected)
