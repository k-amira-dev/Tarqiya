"""Password hashing with argon2id (the current OWASP recommendation).

WHY HASH? We never store a password. We store a "hash": a one-way scrambled version that cannot be turned back into the
password. To check a login we scramble what the user typed and compare the two scrambles. If the database ever leaked,
the passwords would still not be readable. argon2id is deliberately slow, which makes guessing passwords expensive.
"""
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# One shared hasher with sensible default settings (cost, salt). The salt is random per password and is stored
# inside the hash string.
_hasher = PasswordHasher()


# Turn a plain password into the string we store in the database.
def hash_password(password: str) -> str:
    return _hasher.hash(password)


# True if `password` matches the stored hash. Any problem (wrong password, corrupted hash) simply returns False; it
# never reveals which.
def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


# True if the stored hash was made with older, weaker settings. authenticate() then re-hashes it on the next
# successful login.
def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)
