from collections.abc import Iterable
from pathlib import Path


class LocalObjectStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def put(self, key: str, source: Iterable[bytes]) -> int:
        destination = self.root / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        with destination.open("wb") as output:
            for chunk in source:
                output.write(chunk)
                size += len(chunk)
        return size

    def get(self, key: str) -> Path:
        path = self.root / key
        if not path.is_file():
            raise FileNotFoundError(key)
        return path

    def list(self, prefix: str) -> list[str]:
        base = self.root / prefix
        if not base.exists():
            return []
        return [
            str(path.relative_to(self.root))
            for path in base.rglob("*")
            if path.is_file()
        ]

    def size(self, key: str) -> int:
        return self.get(key).stat().st_size
