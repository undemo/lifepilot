import os
from pathlib import Path

from fastapi import Request

from app.core.data_paths import DATA_DIR
from app.services.container import ServiceContainer


def get_container(request: Request) -> ServiceContainer:
    return request.app.state.container


def default_data_dir() -> Path:
    override = os.getenv("LIFEPILOT_DATA_DIR")
    if override:
        return Path(override)
    return DATA_DIR
