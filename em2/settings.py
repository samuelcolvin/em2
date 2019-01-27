from atoolbox import BaseSettings


class Settings(BaseSettings):
    domain: str = 'localhost'
    commit: str = 'unknown'
    build_time: str = 'unknown'
