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
        logger.info(f"Published:\n{event_type}")
        
        if event_type not in self._subscribers:
            logger.info(f"Subscribers:\nNone")
            return
            
        subscribers = self._subscribers[event_type]
        sub_names = [cb.__name__ if hasattr(cb, '__name__') else type(cb).__name__ for cb in subscribers]
        logger.info(f"Subscribers:\n{', '.join(sub_names)} (Count: {len(subscribers)})")
        
        for callback in subscribers:
            cb_name = callback.__name__ if hasattr(callback, '__name__') else type(callback).__name__
            try:
                logger.info(f"Subscriber execution started: {cb_name}")
                callback(event_data)
                logger.info(f"Subscriber execution finished: {cb_name}")
            except Exception as e:
                logger.exception(f"Error executing callback {cb_name} for event {event_type}")
                raise
                
        logger.info(f"Event completion: {event_type}")

# Global instance for ease of use across the application
event_bus = EventBus()
