# Default event bus module

class DefaultEventBus:
    def __init__(self, handlers):
        self._handlers = handlers or {}
    
    def emit(self, event):
        name = event.type if hasattr(event, 'type') else str(event)
        for handler in self._handlers.get(name, []):
            handler(event)