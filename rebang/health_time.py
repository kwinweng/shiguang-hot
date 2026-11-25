"""Time validation for collection health observations."""
from datetime import timedelta

MAX_CLOCK_SKEW = timedelta(minutes=5)


def observation_time(moment, now):
    """Normalize a timestamp to the build timezone and reject implausible values."""
    if moment is None or moment.tzinfo is None:
        return None
    try:
        moment = moment.astimezone(now.tzinfo)
        return moment if moment - now <= MAX_CLOCK_SKEW else None
    except (ValueError, OverflowError):
        return None
