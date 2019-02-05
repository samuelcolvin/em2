from pathlib import Path

from atoolbox import BaseSettings

SRC_DIR = Path(__file__).parent


class Settings(BaseSettings):
    pg_dsn = 'postgres://postgres@localhost:5432/em2'
    cookie_name = 'em2'
    sql_path = SRC_DIR / 'models.sql'
    create_app = 'em2.main.create_app'

    domain: str = 'localhost'
    commit: str = 'unknown'
    build_time: str = 'unknown'

    # used for hashing when the user in the db has no password, or no user is found
    dummy_password = '__dummy_password__'
    bcrypt_work_factor = 12
    # login attempts per minute allowed before grecaptcha is required
    easy_login_attempts = 3
    # max. login attempts allowed per minute
    max_login_attempts = 20

    class Config:
        env_prefix = 'em2_'
        case_insensitive = True
