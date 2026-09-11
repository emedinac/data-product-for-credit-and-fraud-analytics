class LocalEventPublisher:
    def publish(self, batch_id: str) -> None:
        # This direct call is the local stand-in for a future Pub/Sub message.
        return None
