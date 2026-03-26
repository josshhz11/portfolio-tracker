"""Date/time helpers used across the portfolio tracker."""

from datetime import date, datetime, timezone


def today_str() -> str:
    """Return today's date as an ISO-8601 string (``YYYY-MM-DD``).

    The date is derived from UTC so that scheduled runs behave consistently
    regardless of the host timezone.

    Returns:
        Today's date string, e.g. ``"2024-01-15"``.
    """
    return datetime.now(tz=timezone.utc).date().isoformat()


def date_from_str(date_str: str) -> date:
    """Parse an ISO-8601 date string into a :class:`datetime.date` object.

    Args:
        date_str: A string in the form ``YYYY-MM-DD``.

    Returns:
        Corresponding :class:`datetime.date`.

    Raises:
        ValueError: If *date_str* is not a valid ISO-8601 date.
    """
    return date.fromisoformat(date_str)


def is_valid_date_str(date_str: str) -> bool:
    """Return ``True`` if *date_str* is a valid ``YYYY-MM-DD`` string.

    Args:
        date_str: The string to validate.

    Returns:
        ``True`` when valid, ``False`` otherwise.
    """
    try:
        date_from_str(date_str)
        return True
    except ValueError:
        return False
