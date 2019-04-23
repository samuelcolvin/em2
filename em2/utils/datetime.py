from datetime import datetime, timezone

EPOCH = datetime(1970, 1, 1)
EPOCH_TZ = EPOCH.replace(tzinfo=timezone.utc)


def _to_unix_float(dt: datetime) -> float:
    if dt.utcoffset() is None:
        diff = dt - EPOCH
    else:
        diff = dt - EPOCH_TZ
    return diff.total_seconds()


def to_unix_ms(dt: datetime) -> int:
    return int(_to_unix_float(dt) * 1000)


def to_unix_s(dt: datetime) -> int:
    return int(round(_to_unix_float(dt)))


def utcnow():
    return datetime.utcnow().replace(tzinfo=timezone.utc)
