from datetime import datetime, timezone

EPOCH = datetime(1970, 1, 1)
EPOCH_TZ = EPOCH.replace(tzinfo=timezone.utc)


def to_unix_ms(dt: datetime) -> int:
    if dt.utcoffset() is None:
        diff = dt - EPOCH
    else:
        diff = dt - EPOCH_TZ
    return int(diff.total_seconds() * 1000)
