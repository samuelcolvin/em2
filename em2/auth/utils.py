import bcrypt

from settings import Settings


def mk_password(password: str, settings: Settings) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=settings.bcrypt_work_factor)).decode()
