import secrets
from datetime import timedelta
from pathlib import Path
from secrets import token_urlsafe
from typing import Optional

from atoolbox import BaseSettings
from pydantic import EmailStr, constr

SRC_DIR = Path(__file__).parent


class Settings(BaseSettings):
    pg_dsn = 'postgres://postgres@localhost:5432/em2'
    cookie_name = 'em2'
    sql_path = SRC_DIR / 'models.sql'
    create_app = 'em2.main.create_app'
    worker_func = 'em2.worker.run_worker'
    patch_paths = ['em2.auth.patches']
    auth_key = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa='

    domain: str = 'localhost'  # currently used as a proxy for development mode, should probably be changed
    testing: bool = False  # used only in unit test eg, to use http not https for the em2 protocol
    any_origin: bool = False  # WARNING: this is dangerous, only use when testing
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
    # how long micro session can last before they need to be checked with auth
    micro_session_duration = 60 * 15
    # how many seconds until an idle session expires
    session_expiry = 86400 * 4
    # used for testing only to slow down the UI app
    slow_ui: int = None

    internal_auth_key: constr(min_length=40, max_length=100) = secrets.token_urlsafe()

    # em2 feature settings:
    message_lock_duration: int = 3600  # how many seconds a lock holds for

    smtp_handler = 'em2.protocol.smtp.LogSmtpHandler'
    aws_access_key: str = None
    aws_secret_key: str = None
    aws_region: str = 'us-east-1'
    # set here so they can be overridden during tests
    ses_host = 'email.{region}.amazonaws.com'
    ses_endpoint_url = 'https://{host}/'
    ses_configuration_set = 'em2'
    smtp_message_id_domain = 'email.amazonses.com'
    s3_endpoint_url: str = None  # only used when testing
    s3_temp_bucket: str = None
    s3_temp_bucket_lifetime: timedelta = 'P30D'
    s3_file_bucket: str = None
    # generate randomly to avoid leaking secrets:
    ses_url_token: str = token_urlsafe()
    aws_sns_signing_host = '.amazonaws.com'
    aws_sns_signing_schema = 'https'
    s3_cache_bucket: str = None
    max_ref_image_size = 10 * 1024 ** 2
    max_ref_image_count = 20

    vapid_private_key: str = None
    vapid_sub_email: EmailStr = None

    class Config:
        env_prefix = 'em2_'
        case_insensitive = True
