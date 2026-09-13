import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import cast

from google.cloud.storage import Client  # type: ignore[import-untyped]


class GCSObjectStorage:
    def __init__(self, bucket_name: str) -> None:
        self.client = Client()
        self.bucket = self.client.bucket(bucket_name)

    def put(self, key: str, source: Iterable[bytes]) -> int:
        size = 0
        with tempfile.NamedTemporaryFile() as temporary:
            for chunk in source:
                temporary.write(chunk)
                size += len(chunk)
            temporary.flush()
            self.bucket.blob(key).upload_from_filename(temporary.name)
        return size

    def get(self, key: str) -> Path:
        temporary = tempfile.NamedTemporaryFile(delete=False)
        temporary.close()
        path = Path(temporary.name)
        blob = self.bucket.blob(key)
        if not blob.exists():
            path.unlink(missing_ok=True)
            raise FileNotFoundError(key)
        blob.download_to_filename(path)
        return path

    def list(self, prefix: str) -> list[str]:
        return [
            blob.name for blob in self.client.list_blobs(self.bucket, prefix=prefix)
        ]

    def size(self, key: str) -> int:
        blob = self.bucket.get_blob(key)
        if blob is None or blob.size is None:
            raise FileNotFoundError(key)
        return cast(int, blob.size)
