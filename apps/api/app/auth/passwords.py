"""Fixed-cost scrypt password hashes using the existing cryptography dependency."""
import base64
import hmac
import os
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


def derive(password: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=2**17, r=8, p=1).derive(password.encode())


def password_hash(password: str) -> str:
    salt = os.urandom(16)
    return 'scrypt$131072$8$1$' + base64.urlsafe_b64encode(salt).decode() + '$' + base64.urlsafe_b64encode(derive(password, salt)).decode()


def parse_hash(value: str):
    try:
        algorithm, n, r, p, salt, digest = value.split('$')
        if (algorithm,n,r,p) != ('scrypt','131072','8','1'):
            raise ValueError
        salt = base64.b64decode(salt, altchars=b'-_', validate=True)
        digest = base64.b64decode(digest, altchars=b'-_', validate=True)
        if len(salt) != 16 or len(digest) != 32:
            raise ValueError
        return salt, digest
    except (ValueError, TypeError):
        raise ValueError('Invalid dashboard password hash') from None


def verify(password: str, value: str) -> bool:
    salt, digest = parse_hash(value)
    return hmac.compare_digest(derive(password, salt), digest)
