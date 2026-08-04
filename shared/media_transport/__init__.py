"""Media Distribution Interface (ADR-028).

Every cross-process media exchange in the Media Architecture Reset goes
through this package's contract (``interface.py``), never through a
transport-specific assumption baked into a consumer. RTSP
(``rtsp.py``) is the Phase 1 implementation, not the architectural
contract -- later implementations (shared memory, UDP/RTP, SRT, QUIC,
Unix sockets, zero-copy) can replace or supplement it without changing
any consumer's code, since consumers only ever hold a ``MediaEndpoint``
and call ``build_source_element()`` on it.
"""

from __future__ import annotations

from shared.media_transport.interface import MediaEndpoint, MediaPublisher, build_source_element

__all__ = ["MediaEndpoint", "MediaPublisher", "build_source_element"]
