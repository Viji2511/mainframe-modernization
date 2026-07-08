from typing import Callable, Dict, List, Any
import logging

logger = logging.getLogger(__name__)

class EventBus:
    """
    Lightweight in-memory publish/subscribe event bus.
    """
    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[Any], None]]] = {}

    def subscribe(self, event_type: str, callback: Callable[[Any], None]) -> None:
        """
        Subscribe a callback function to a specific event type.
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
        logger.debug(f"Subscribed to {event_type}. Total subscribers: {len(self._subscribers[event_type])}")

    def publish(self, event_type: str, event_data: Any) -> None:
        """
        Publish an event to all registered subscribers.
        """
        if event_type not in self._subscribers:
            logger.debug(f"No subscribers for event: {event_type}")
            return
            
        for callback in self._subscribers[event_type]:
            try:
                callback(event_data)
            except Exception as e:
                logger.error(f"Error executing callback for event {event_type}: {str(e)}")

# Global instance for ease of use across the application
event_bus = EventBus()
