"""Interactive hash generation; password never enters shell history or stdout."""
from getpass import getpass
from app.auth.passwords import password_hash

if __name__ == '__main__':
    password = getpass('Dashboard password (at least 12 characters): ')
    confirmation = getpass('Confirm password: ')
    if len(password) < 12 or password != confirmation:
        raise SystemExit('Use at least 12 characters and matching confirmation.')
    print(password_hash(password))
