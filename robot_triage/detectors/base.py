"""Detector base class.

process() is called once per message in log order; finish() returns the events.
Streaming like this means we never hold a whole (potentially huge) bag in memory.
"""

from abc import ABC, abstractmethod


class Detector(ABC):
    #: Short identifier, copied onto every Event this detector emits.
    name = "detector"

    @abstractmethod
    def process(self, topic, t, msg):
        """Consume one message: ``topic`` (str), ``t`` (seconds), ``msg`` (decoded)."""
        raise NotImplementedError

    def finish(self):
        """Return a list of Events found once the stream is exhausted."""
        return []
