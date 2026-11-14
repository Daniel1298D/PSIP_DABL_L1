"""Single local account for the GeoAnaliza desktop application."""

from contextlib import closing
import hashlib
import hmac
from pathlib import Path
import secrets
import sqlite3


class Accounts:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('''CREATE TABLE IF NOT EXISTS account (
                id INTEGER PRIMARY KEY CHECK (id = 1), username TEXT NOT NULL,
                salt BLOB NOT NULL, password_hash BLOB NOT NULL)''')

    def record(self):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute('SELECT username, salt, password_hash FROM account WHERE id = 1').fetchone()

    @staticmethod
    def derive(password, salt):
        return hashlib.scrypt(password.encode('utf-8'), salt=salt, n=16384, r=8, p=1, dklen=32)

    def create(self, username, password):
        if not 3 <= len(username) <= 64 or not 8 <= len(password) <= 256:
            raise ValueError('Nazwa użytkownika musi mieć 3–64 znaki, a hasło 8–256 znaków.')
        salt = secrets.token_bytes(16)
        digest = self.derive(password, salt)
        with closing(sqlite3.connect(self.path)) as db, db:
            result = db.execute('INSERT OR IGNORE INTO account VALUES (1, ?, ?, ?)', (username, salt, digest))
            if result.rowcount != 1:
                raise ValueError('Konto już istnieje. Przejdź do logowania.')

    def verify(self, username, password):
        record = self.record()
        if record is None or len(password) > 256:
            return False
        saved_name, salt, digest = record
        matches = hmac.compare_digest(self.derive(password, salt), digest)
        return matches and username == saved_name
