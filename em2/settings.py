from atoolbox import BaseSettings


class Settings(BaseSettings):
    pg_dsn = 'postgres://postgres@localhost:5432/em2'
    cookie_name = 'em2'

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
