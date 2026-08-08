"""Production EventBus broker -- ADR-029 Phase 4.

A standalone ZMQ XSUB/XPUB forwarder (the standard ``zmq.proxy`` device).
Every ``ZmqEventBus`` publisher connects a PUB socket to this process's
XSUB bind; every subscriber connects a SUB socket to its XPUB bind.
``zmq.proxy`` forwards raw byte frames end to end -- topic filtering
(which subscriber receives which ``event_type``) happens via libzmq's own
subscription-prefix mechanism inside the proxy, a byte-prefix match, not
a schema-aware decision.

This module imports only ``zmq`` -- never ``shared.events`` or any event
class. All (de)serialization lives exclusively in ``ZmqEventBus``, inside
each producer/consumer process (a required architecture correction: the
bus -- including this broker -- is transport only, per ADR-029's
governing principle "the EventBus is transport only").

This is what makes producers and consumers mutually unaware of each
other's identity: a publisher only ever knows "connect to the broker and
send with topic=event_type"; a subscriber only ever knows "connect to the
broker and filter by topic=event_type." Adding a new event type or a new
subsystem touches neither this broker nor any registry.

Run with:
    python -m shared.events.broker
"""

from __future__ import annotations

import logging

import zmq

from shared.events.config import EVENT_BUS_HOST, EVENT_BUS_PUBLISH_PORT, EVENT_BUS_SUBSCRIBE_PORT

logger = logging.getLogger(__name__)


def run_broker(
    *,
    host: str = EVENT_BUS_HOST,
    publish_port: int = EVENT_BUS_PUBLISH_PORT,
    subscribe_port: int = EVENT_BUS_SUBSCRIBE_PORT,
) -> None:
    """Bind XSUB/XPUB and forward forever. Blocks until interrupted."""
    context = zmq.Context()
    xsub = context.socket(zmq.XSUB)
    xsub.bind(f"tcp://{host}:{publish_port}")
    xpub = context.socket(zmq.XPUB)
    xpub.bind(f"tcp://{host}:{subscribe_port}")
    logger.info(
        "radar-eye-event-bus running",
        extra={"publish_port": publish_port, "subscribe_port": subscribe_port},
    )
    try:
        zmq.proxy(xsub, xpub)
    finally:
        xsub.close()
        xpub.close()
        context.term()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    run_broker()


if __name__ == "__main__":
    main()
