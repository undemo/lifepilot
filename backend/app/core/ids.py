from uuid import uuid4

from .time import id_date


def new_id(prefix: str) -> str:
    return f"{prefix}_{id_date()}_{uuid4().hex[:8]}"

