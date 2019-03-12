from pathlib import Path
from secrets import token_urlsafe
from typing import Optional

from atoolbox import BaseSettings

SRC_DIR = Path(__file__).parent


class Settings(BaseSettings):
    pg_dsn = 'postgres://postgres@localhost:5432/em2'
    cookie_name = 'em2'
    sql_path = SRC_DIR / 'models.sql'
    create_app = 'em2.main.create_app'

    domain: str = 'localhost'  # currently used as a proxy for development mode, should probably be changed
    local_port: Optional[int] = 8000
    commit: str = 'unknown'
    build_time: str = 'unknown'
    # used for hashing when the user in the db has no password, or no user is found
    dummy_password = '__dummy_password__'
    bcrypt_work_factor = 12
    # login attempts per minute allowed before grecaptcha is required
    easy_login_attempts = 3
    # max. login attempts allowed per minute
    max_login_attempts = 20

    # em2 feature settings:
    message_lock_duration: int = 3600  # how many seconds a lock holds for

    fallback_handler = 'em2.protocol.fallback.LogFallbackHandler'
    aws_access_key: str = None
    aws_secret_key: str = None
    aws_region: str = 'us-east-1'
    # set here so they can be overridden during tests
    ses_host = 'email.{region}.amazonaws.com'
    ses_endpoint_url = 'https://{host}/'
    s3_endpoint_url: str = None  # only used when testing
    # generate randomly to avoid leaking secrets:
    ses_url_token: str = token_urlsafe()
    aws_sns_signing_host = '.amazonaws.com'
    aws_sns_signing_schema = 'https'

    class Config:
        env_prefix = 'em2_'
        case_insensitive = True
