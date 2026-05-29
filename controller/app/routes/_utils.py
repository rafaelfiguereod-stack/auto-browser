from __future__ import annotations

import re
from logging import Logger

from fastapi import HTTPException

_SAFE_PATH_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def require_safe_segment(value: str, *, field: str) -> str:
    """Validate that *value* is a single safe path segment."""
    if not isinstance(value, str) or not _SAFE_PATH_SEGMENT.fullmatch(value):
        raise HTTPException(status_code=400, detail=f"Invalid {field}")
    return value


def internal_error(logger: Logger, message: str, *args: object) -> HTTPException:
    logger.exception(message, *args)
    return HTTPException(status_code=500, detail="Internal error")
