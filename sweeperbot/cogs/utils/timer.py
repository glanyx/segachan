import asyncio
import datetime
from typing import Callable

from . import time


class Timer:
    __slots__ = ("args", "event", "id", "created_at", "expires", "_timer")

    def __init__(self, *, record):
        self.id = id(self)

        self.event = record["event"]
        self.created_at = record["created"]
        self.expires = record["expires"]
        self.args = record["args"]

    @classmethod
    def temporary(
        cls,
        *args,
        expires: datetime.datetime,
        created: datetime.datetime,
        event: Callable[..., None],
    ):
        pseudo = {"created": created, "expires": expires, "event": event, "args": args}
        return cls(record=pseudo)

    def __eq__(self, other):
        try:
            return self.id == other.id
        except AttributeError:
            return False

    def __hash__(self):
        return hash(self.id)

    def __bool__(self):
        return (
            self.expires - datetime.datetime.now(datetime.timezone.utc)
        ).total_seconds() > 0

    @property
    def human_delta(self):
        return time.human_timedelta(self.expires)

    def __repr__(self):
        return f"<Timer {self.id} created={self.created_at} expires={self.expires} event={self.event}>"

    def start(self, loop: asyncio.BaseEventLoop):
        # we don't call self.event directly, because call_later has a max waiting time of 1 day
        # (see https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.time)
        # So we check if the timer needs to be rescheduled.
        delta = self.expires - datetime.datetime.now(datetime.timezone.utc)
        if delta.total_seconds() <= 0:
            self.event(*self.args)
        else:
            # loop.call_later((self.expires - datetime.utcnow()).total_seconds(), self.event, *self.args)
            self._timer = loop.call_later(delta.total_seconds(), self.start, loop)

    def stop(self):
        if not self._timer.cancelled():
            self._timer.cancel()
