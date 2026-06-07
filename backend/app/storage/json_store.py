import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Union

from app.core.data_paths import DATA_DIR, DATA_FILE_PATHS


class JsonFileStore:
    def __init__(self, data_dir: Path, file_paths: Optional[Mapping[str, Path]] = None) -> None:
        self.data_dir = Path(data_dir)
        self.file_paths = dict(file_paths or DATA_FILE_PATHS)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, filename: Union[str, Path]) -> Path:
        path = Path(filename)
        if not path.is_absolute() and len(path.parts) == 1:
            configured = self.file_paths.get(path.name)
            if configured is not None:
                return self._resolve_configured_path(configured)
            return self.data_dir / path
        return self._resolve_configured_path(path)

    def _resolve_configured_path(self, path: Path) -> Path:
        if path.is_absolute():
            try:
                relative_path = path.relative_to(DATA_DIR)
            except ValueError:
                return path
            return self.data_dir / relative_path
        return self.data_dir / path

    def read(self, filename: Union[str, Path], default: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            path = self._path(filename)
            if not path.exists():
                if not self._can_initialize(path):
                    raise FileNotFoundError(f"Required data file is missing: {path}")
                self.write(filename, default)
                return dict(default)
            try:
                with path.open("r", encoding="utf-8") as file:
                    return json.load(file)
            except json.JSONDecodeError:
                corrupt_path = path.with_suffix(path.suffix + f".corrupt.{uuid.uuid4().hex[:8]}")
                os.replace(path, corrupt_path)
                if not self._can_initialize(path):
                    raise ValueError(f"Required data file is corrupt: {corrupt_path}")
                self.write(filename, default)
                return dict(default)

    def _can_initialize(self, path: Path) -> bool:
        try:
            relative = path.relative_to(self.data_dir)
        except ValueError:
            return False
        return bool(relative.parts) and relative.parts[0] == "runtime"

    def write(self, filename: Union[str, Path], payload: Dict[str, Any]) -> None:
        with self._lock:
            path = self._path(filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_suffix(path.suffix + f".{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex[:8]}.tmp")
            with tmp_path.open("w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2)
                file.write("\n")
            os.replace(tmp_path, path)
