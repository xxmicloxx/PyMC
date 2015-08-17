import heapq


class Cancelable(object):
    def __init__(self):
        super(Cancelable, self).__init__()
        self.cancelled = False


class Event(object):
    def __init__(self):
        self.handlers = list()
        self.handler_finder = dict()

    def handle(self, my_handler, priority=0, ignore_cancelled=True):
        if my_handler in self.handler_finder:
            self.unhandle(my_handler)

        task = (priority, my_handler, {"ignore_cancelled": ignore_cancelled})
        heapq.heappush(self.handlers, task)
        self.handler_finder[my_handler] = task

    def unhandle(self, my_handler):
        try:
            task = self.handler_finder.pop(my_handler)
            self.handlers.remove(task)
        except:
            raise ValueError("Handler is not handling this event, so cannot unhandle.")
        return self

    def fire(self, obj):
        for priority, my_handler, properties in self.handlers:
            if isinstance(obj, Cancelable) and obj.cancelled and properties['ignore_cancelled']:
                continue

            my_handler(obj)

    @property
    def handler_count(self):
        return len(self.handlers)

    __call__ = fire
    __len__ = handler_count


def handler(event, priority=0, ignore_cancelled=True):
    def wrap(f):
        event.handle(f, priority=priority, ignore_cancelled=ignore_cancelled)
        return f
    return wrap
