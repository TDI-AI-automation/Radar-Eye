"""Production EventBus transport config -- ADR-029 Phase 4.

Deployment/network configuration only -- deliberately holds zero
knowledge of event types or schemas (that split is a required
architecture correction: event metadata and transport addressing are
separate concerns). Fixed, deploy-time values, same idea as ``run.py``'s
existing hardcoded ``INGESTION_PORT``/``LIVE_STREAMING_PORT`` constants.

Both ports are bound by ``shared.events.broker`` (a ZMQ XSUB/XPUB
forwarder): publishers connect a PUB socket to ``EVENT_BUS_PUBLISH_PORT``
(the broker's XSUB bind); subscribers connect a SUB socket to
``EVENT_BUS_SUBSCRIBE_PORT`` (the broker's XPUB bind). Neither producers
nor consumers ever need each other's address -- only the broker's.
"""

from __future__ import annotations

EVENT_BUS_HOST = "127.0.0.1"
EVENT_BUS_PUBLISH_PORT = 5901
"""Publishers (PUB sockets) connect here -- the broker's XSUB bind."""

EVENT_BUS_SUBSCRIBE_PORT = 5902
"""Subscribers (SUB sockets) connect here -- the broker's XPUB bind."""
