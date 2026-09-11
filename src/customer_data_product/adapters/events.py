from collections.abc import Callable


class LocalEventPublisher:
    def __init__(self) -> None:
        self._handler: Callable[[str], None] | None = None

    def set_handler(self, handler: Callable[[str], None]) -> None:
        self._handler = handler

    def publish(self, batch_id: str) -> None:
        # This direct call is the local stand-in for a future Pub/Sub message.
        return None
