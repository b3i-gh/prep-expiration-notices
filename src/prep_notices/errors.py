class NoticeError(Exception):
    """An actionable error safe to display without raw provider responses."""


class ApiError(NoticeError):
    """A failed remote operation."""


class UncertainInsert(ApiError):
    """The provider may have committed the insertion."""
