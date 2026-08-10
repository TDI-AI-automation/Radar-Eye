"""Event-type -> envelope-class lookup, for deserializing an incoming
``ZmqEventBus`` frame into the correctly-typed ``EventEnvelope[Payload]``.

Derived automatically from ``shared.events.types.__all__`` rather than a
second, hand-maintained mapping (a required architecture correction --
adding a new event only ever requires the one edit already needed to
define it in ``types.py``; nothing here needs touching).
"""

from __future__ import annotations

from shared.events import types as _types
from shared.events.envelope import EventEnvelope

EVENT_CLASS_BY_TYPE: dict[str, type[EventEnvelope]] = {
    name: getattr(_types, name) for name in _types.__all__
}
