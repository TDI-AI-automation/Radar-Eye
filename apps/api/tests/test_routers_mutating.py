"""Tests for the Phase 4 mutating routers -- RM-12
(cameras PATCH, incidents PATCH, reviews PATCH/POST actions,
calibration start/validate).

Router-level (real ``create_app()``, real DB), matching
test_router_auth.py's/test_routers_read_only.py's established pattern.

Every mutating route writes an ``audit_log`` row whose ``actor_user_id``
carries a real foreign key to ``users.id`` -- unlike the read-only routers'
tests, these must seed a real ``User`` row and issue a token for *that*
user's id (not an arbitrary ``uuid.uuid4()``, which the read-only routers'
``auth_header`` fixture uses safely only because those routes never write
to ``audit_log``). Discovered live against a real database while
implementing Phase 4: a token for a nonexistent user_id fails with an
unhandled ``ForeignKeyViolationError`` the moment any mutating route tries
to audit-log it.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.config import get_settings
from apps.api.app.main import create_app
from apps.api.app.models.camera import Camera
from apps.api.app.models.human_review import HumanReviewItem
from apps.api.app.models.incident import Incident
from apps.api.app.models.user import ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER, User
from apps.api.app.repositories.audit_log import AuditLogRepository
from apps.api.app.repositories.camera import CameraRepository, CameraStreamProfileRepository
from apps.api.app.routers.cameras import get_webrtc_proxy_client
from apps.api.app.security.auth import create_token_pair, hash_password
from shared.constants.incident_types import IncidentStatus, IncidentType
from shared.constants.threat_levels import ThreatLevel


async def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def _make_user(session: AsyncSession, role: str) -> User:
    user = User(
        username=f"user-{uuid.uuid4().hex[:8]}", password_hash=hash_password("x"), role=role
    )
    session.add(user)
    await session.commit()
    return user


def _auth_header(user: User, role: str) -> dict[str, str]:
    tokens = create_token_pair(user_id=user.id, role=role, settings=get_settings())
    return {"Authorization": f"Bearer {tokens.access_token}"}


async def _make_camera(session: AsyncSession, **overrides) -> Camera:
    camera = Camera(name="cam-1", location="north gate", status="CONNECTED", **overrides)
    session.add(camera)
    await session.commit()
    return camera


async def _make_camera_with_profile(session: AsyncSession, **overrides) -> Camera:
    from apps.api.app.config import get_settings as _get_settings
    from apps.api.app.models.camera import CameraStreamProfile
    from apps.api.app.security.encryption import get_credential_encryption_provider

    camera = await _make_camera(session, **overrides)
    encryption = get_credential_encryption_provider(_get_settings())
    profile = CameraStreamProfile(
        camera_id=camera.id,
        rtsp_url_encrypted=encryption.encrypt("rtsp://admin:hunter2@192.0.2.10:554/stream1"),
        transport="tcp",
        brand="HIKVISION",
        model="DS-2CD2143G0-I",
        ip_address="192.0.2.10",
        port=554,
        stream_path="/stream1",
        username="admin",
        password_encrypted=encryption.encrypt("hunter2"),
    )
    session.add(profile)
    await session.commit()
    return camera


async def _make_incident(session: AsyncSession, camera: Camera, **overrides) -> Incident:
    fields = {
        "camera_id": camera.id,
        "track_id": 1,
        "incident_type": IncidentType.THREAT,
        "threat_level": ThreatLevel.HIGH,
        "status": IncidentStatus.ACTIVE,
        "threat_summary": {},
    }
    fields.update(overrides)
    incident = Incident(**fields)
    session.add(incident)
    await session.commit()
    return incident


async def _make_review(session: AsyncSession, camera: Camera) -> HumanReviewItem:
    item = HumanReviewItem(camera_id=camera.id, track_id=2, reason="uniform_unknown")
    session.add(item)
    await session.commit()
    return item


@pytest.mark.asyncio
class TestCamerasPatch:
    async def test_requires_authentication(self, db_engine, db_session) -> None:
        camera = await _make_camera(db_session)
        app = create_app()
        async with await _client(app) as client:
            response = await client.patch(f"/cameras/{camera.id}", json={"location": "x"})
        assert response.status_code == 401

    async def test_rejects_non_admin(self, db_engine, db_session) -> None:
        camera = await _make_camera(db_session)
        operator = await _make_user(db_session, ROLE_OPERATOR)
        app = create_app()
        async with await _client(app) as client:
            response = await client.patch(
                f"/cameras/{camera.id}",
                json={"location": "x"},
                headers=_auth_header(operator, ROLE_OPERATOR),
            )
        assert response.status_code == 403

    async def test_admin_updates_camera_and_writes_audit_row(self, db_engine, db_session) -> None:
        camera = await _make_camera(db_session)
        admin = await _make_user(db_session, ROLE_ADMIN)
        app = create_app()
        async with await _client(app) as client:
            response = await client.patch(
                f"/cameras/{camera.id}",
                json={"location": "south gate"},
                headers=_auth_header(admin, ROLE_ADMIN),
            )

        assert response.status_code == 200
        assert response.json()["data"]["location"] == "south gate"

        entries = await AuditLogRepository(db_session).list()
        matching = [
            e for e in entries if e.action == "UPDATE_CAMERA" and e.actor_user_id == admin.id
        ]
        assert len(matching) == 1
        assert matching[0].details == {"location": "south gate"}

    async def test_admin_toggles_desired_state_flags(self, db_engine, db_session) -> None:
        """RM-12 Runtime State Model -- ai_enabled/recording_enabled are
        Desired state, operator-configurable via the same general PATCH
        route as name/location; no dedicated endpoint, no Camera Runtime
        call, no event published by this route -- these are plain
        persisted fields."""
        camera = await _make_camera(db_session)
        admin = await _make_user(db_session, ROLE_ADMIN)
        app = create_app()
        async with await _client(app) as client:
            response = await client.patch(
                f"/cameras/{camera.id}",
                json={"ai_enabled": True, "recording_enabled": True},
                headers=_auth_header(admin, ROLE_ADMIN),
            )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["ai_enabled"] is True
        assert data["recording_enabled"] is True

    async def test_editing_ip_regenerates_url_and_preserves_password(
        self, db_engine, db_session
    ) -> None:
        camera = await _make_camera_with_profile(db_session)
        admin = await _make_user(db_session, ROLE_ADMIN)
        app = create_app()
        async with await _client(app) as client:
            response = await client.patch(
                f"/cameras/{camera.id}",
                json={"ip_address": "192.0.2.99"},
                headers=_auth_header(admin, ROLE_ADMIN),
            )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["ip_address"] == "192.0.2.99"
        assert "password" not in data

        from apps.api.app.config import get_settings as _get_settings
        from apps.api.app.security.encryption import get_credential_encryption_provider

        profile = await CameraStreamProfileRepository(db_session).get_by_camera_id(camera.id)
        assert profile is not None
        encryption = get_credential_encryption_provider(_get_settings())
        url = encryption.decrypt(profile.rtsp_url_encrypted)
        assert "192.0.2.99" in url
        assert "hunter2" in url  # password preserved, not cleared by the omitted field

        entries = await AuditLogRepository(db_session).list()
        matching = [
            e for e in entries if e.action == "UPDATE_CAMERA" and e.actor_user_id == admin.id
        ]
        assert len(matching) == 1
        assert matching[0].details == {"connection_fields_changed": ["ip_address"]}

    async def test_editing_password_never_reaches_audit_log(self, db_engine, db_session) -> None:
        camera = await _make_camera_with_profile(db_session)
        admin = await _make_user(db_session, ROLE_ADMIN)
        app = create_app()
        async with await _client(app) as client:
            response = await client.patch(
                f"/cameras/{camera.id}",
                json={"password": "new-secret-value"},
                headers=_auth_header(admin, ROLE_ADMIN),
            )
        assert response.status_code == 200

        entries = await AuditLogRepository(db_session).list()
        matching = [
            e for e in entries if e.action == "UPDATE_CAMERA" and e.actor_user_id == admin.id
        ]
        assert len(matching) == 1
        assert matching[0].details == {
            "connection_fields_changed": [],
            "password_changed": True,
        }
        assert "new-secret-value" not in str(matching[0].details)

    async def test_returns_404_for_missing_camera(self, db_engine, db_session) -> None:
        admin = await _make_user(db_session, ROLE_ADMIN)
        app = create_app()
        async with await _client(app) as client:
            response = await client.patch(
                "/cameras/00000000-0000-0000-0000-000000000000",
                json={"location": "x"},
                headers=_auth_header(admin, ROLE_ADMIN),
            )
        assert response.status_code == 404

    async def test_editing_model_is_purely_descriptive(self, db_engine, db_session) -> None:
        """model is stored on the same profile row as the connection
        fields but plays no part in RTSP URL generation -- editing it alone
        must not disturb the existing URL/password."""
        camera = await _make_camera_with_profile(db_session)
        admin = await _make_user(db_session, ROLE_ADMIN)
        app = create_app()
        async with await _client(app) as client:
            response = await client.patch(
                f"/cameras/{camera.id}",
                json={"model": "DS-2CD2386G2-IU"},
                headers=_auth_header(admin, ROLE_ADMIN),
            )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["model"] == "DS-2CD2386G2-IU"
        assert data["ip_address"] == "192.0.2.10"

        from apps.api.app.config import get_settings as _get_settings
        from apps.api.app.security.encryption import get_credential_encryption_provider

        profile = await CameraStreamProfileRepository(db_session).get_by_camera_id(camera.id)
        assert profile is not None
        encryption = get_credential_encryption_provider(_get_settings())
        url = encryption.decrypt(profile.rtsp_url_encrypted)
        assert "hunter2" in url  # password preserved


@pytest.mark.asyncio
class TestCamerasPost:
    """Camera Registry -- RM-12. POST /cameras is the fix for the gap the
    RM-12 gap analysis found: no API path to register a camera existed
    before this, only the out-of-band scripts/siv_register_camera.py."""

    _BODY = {
        "name": "gate-cam-1",
        "location": "north gate",
        "brand": "HIKVISION",
        "model": "DS-2CD2143G0-I",
        "ip_address": "192.0.2.10",
        "username": "admin",
        "password": "hunter2",
        "transport": "tcp",
    }

    async def test_requires_authentication(self, db_engine, db_session) -> None:
        app = create_app()
        async with await _client(app) as client:
            response = await client.post("/cameras", json=self._BODY)
        assert response.status_code == 401

    async def test_rejects_non_admin(self, db_engine, db_session) -> None:
        operator = await _make_user(db_session, ROLE_OPERATOR)
        app = create_app()
        async with await _client(app) as client:
            response = await client.post(
                "/cameras", json=self._BODY, headers=_auth_header(operator, ROLE_OPERATOR)
            )
        assert response.status_code == 403

    async def test_admin_registers_camera_and_writes_audit_row(self, db_engine, db_session) -> None:
        admin = await _make_user(db_session, ROLE_ADMIN)
        app = create_app()
        async with await _client(app) as client:
            response = await client.post(
                "/cameras", json=self._BODY, headers=_auth_header(admin, ROLE_ADMIN)
            )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "gate-cam-1"
        # RM-12 Design Principle 3: adding a camera must never auto-start AI;
        # the same default applies symmetrically to recording.
        assert data["ai_enabled"] is False
        assert data["recording_enabled"] is False
        assert "rtsp_url" not in data and "password" not in data
        assert data["brand"] == "HIKVISION"
        assert data["model"] == "DS-2CD2143G0-I"
        assert data["ip_address"] == "192.0.2.10"
        assert data["username"] == "admin"

        camera = await CameraRepository(db_session).get(uuid.UUID(data["camera_id"]))
        assert camera is not None
        profiles = await CameraStreamProfileRepository(db_session).list()
        profile = next(p for p in profiles if p.camera_id == camera.id)
        assert profile.transport == "tcp"
        assert "hunter2" not in profile.rtsp_url_encrypted  # genuinely ciphertext, not plaintext
        assert profile.rtsp_url_encrypted  # a URL was actually generated and stored
        assert profile.port == 554  # brand default, applied server-side
        assert profile.stream_path == "/Streaming/Channels/101"  # brand default

        entries = await AuditLogRepository(db_session).list()
        matching = [
            e for e in entries if e.action == "REGISTER_CAMERA" and e.actor_user_id == admin.id
        ]
        assert len(matching) == 1

    async def test_duplicate_name_rejected(self, db_engine, db_session) -> None:
        admin = await _make_user(db_session, ROLE_ADMIN)
        app = create_app()
        async with await _client(app) as client:
            first = await client.post(
                "/cameras", json=self._BODY, headers=_auth_header(admin, ROLE_ADMIN)
            )
            assert first.status_code == 200
            second = await client.post(
                "/cameras", json=self._BODY, headers=_auth_header(admin, ROLE_ADMIN)
            )
        assert second.status_code == 409

    async def test_desired_state_flags_can_be_set_explicitly_at_registration(
        self, db_engine, db_session
    ) -> None:
        admin = await _make_user(db_session, ROLE_ADMIN)
        body = {**self._BODY, "name": "gate-cam-2", "ai_enabled": True, "recording_enabled": True}
        app = create_app()
        async with await _client(app) as client:
            response = await client.post(
                "/cameras", json=body, headers=_auth_header(admin, ROLE_ADMIN)
            )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["ai_enabled"] is True
        assert data["recording_enabled"] is True


@pytest.mark.asyncio
class TestCamerasDelete:
    async def test_requires_authentication(self, db_engine, db_session) -> None:
        camera = await _make_camera(db_session)
        app = create_app()
        async with await _client(app) as client:
            response = await client.delete(f"/cameras/{camera.id}")
        assert response.status_code == 401

    async def test_rejects_non_admin(self, db_engine, db_session) -> None:
        camera = await _make_camera(db_session)
        operator = await _make_user(db_session, ROLE_OPERATOR)
        app = create_app()
        async with await _client(app) as client:
            response = await client.delete(
                f"/cameras/{camera.id}", headers=_auth_header(operator, ROLE_OPERATOR)
            )
        assert response.status_code == 403

    async def test_admin_deletes_camera_and_its_profile(self, db_engine, db_session) -> None:
        camera = await _make_camera_with_profile(db_session)
        admin = await _make_user(db_session, ROLE_ADMIN)
        app = create_app()
        async with await _client(app) as client:
            response = await client.delete(
                f"/cameras/{camera.id}", headers=_auth_header(admin, ROLE_ADMIN)
            )

        assert response.status_code == 200
        # The router's own request-scoped session committed the delete on a
        # different session than this test's db_session fixture -- whose
        # identity map still holds the pre-delete objects from
        # _make_camera_with_profile() above. A fresh session, scoped to the
        # same engine, has no stale identity-map entries to return instead
        # of re-querying.
        from apps.api.app.db import create_session_factory

        async with create_session_factory(db_engine)() as fresh_session:
            assert await CameraRepository(fresh_session).get(camera.id) is None
            assert (
                await CameraStreamProfileRepository(fresh_session).get_by_camera_id(camera.id)
                is None
            )

        entries = await AuditLogRepository(db_session).list()
        matching = [
            e for e in entries if e.action == "DELETE_CAMERA" and e.actor_user_id == admin.id
        ]
        assert len(matching) == 1

    async def test_returns_404_for_missing_camera(self, db_engine, db_session) -> None:
        admin = await _make_user(db_session, ROLE_ADMIN)
        app = create_app()
        async with await _client(app) as client:
            response = await client.delete(
                "/cameras/00000000-0000-0000-0000-000000000000",
                headers=_auth_header(admin, ROLE_ADMIN),
            )
        assert response.status_code == 404

    async def test_rejects_deleting_a_camera_with_an_incident(self, db_engine, db_session) -> None:
        """Evidence Preservation (CLAUDE.md) -- deleting a camera must
        never cascade-delete incident history; the database's own foreign
        key constraint is the enforcement mechanism, this route just
        translates the resulting IntegrityError into a clear 409."""
        camera = await _make_camera(db_session)
        await _make_incident(db_session, camera)
        admin = await _make_user(db_session, ROLE_ADMIN)
        app = create_app()
        async with await _client(app) as client:
            response = await client.delete(
                f"/cameras/{camera.id}", headers=_auth_header(admin, ROLE_ADMIN)
            )
        assert response.status_code == 409
        assert await CameraRepository(db_session).get(camera.id) is not None


@pytest.mark.asyncio
class TestCamerasBrands:
    async def test_requires_authentication(self, db_engine, db_session) -> None:
        app = create_app()
        async with await _client(app) as client:
            response = await client.get("/cameras/brands")
        assert response.status_code == 401

    async def test_lists_every_supported_brand_with_defaults(self, db_engine, db_session) -> None:
        viewer = await _make_user(db_session, ROLE_VIEWER)
        app = create_app()
        async with await _client(app) as client:
            response = await client.get(
                "/cameras/brands", headers=_auth_header(viewer, ROLE_VIEWER)
            )
        assert response.status_code == 200
        brands = {b["brand"] for b in response.json()["data"]}
        assert brands == {"HIKVISION", "DAHUA", "UNIVIEW", "AXIS", "HANWHA"}
        for entry in response.json()["data"]:
            assert entry["default_port"] == 554
            assert entry["default_stream_path"]
            assert entry["label"]


class _FakeWebRtcProxyClient:
    """Stands in for httpx.AsyncClient in the webrtc proxy route. Wired in
    via app.dependency_overrides[get_webrtc_proxy_client] rather than
    monkeypatching httpx.AsyncClient.post globally -- the latter would
    also intercept this test file's own _client(app) calls, which are
    themselves httpx.AsyncClient instances."""

    def __init__(self, post_impl) -> None:  # noqa: ANN001
        self._post_impl = post_impl

    async def post(self, url, *, json, timeout):  # noqa: ANN001
        return await self._post_impl(url, json=json, timeout=timeout)


@pytest.mark.asyncio
class TestWebRtcOfferProxy:
    """POST /cameras/{camera_id}/webrtc/offer -- proxies to apps.deepstream's
    local-only signaling server via httpx. Stubs the get_webrtc_proxy_client
    dependency rather than requiring a real deepstream process, matching
    this file's existing "no real external service" testing convention."""

    _BODY = {"sdp": "v=0\r\n...offer...", "type": "offer"}

    async def test_requires_authentication(self, db_engine, db_session) -> None:
        app = create_app()
        async with await _client(app) as client:
            response = await client.post(f"/cameras/{uuid.uuid4()}/webrtc/offer", json=self._BODY)
        assert response.status_code == 401

    async def test_proxies_offer_and_returns_answer(self, db_engine, db_session) -> None:
        viewer = await _make_user(db_session, ROLE_VIEWER)
        camera_id = uuid.uuid4()

        class _FakeResponse:
            status_code = 200

            def json(self) -> dict:
                return {"sdp": "v=0\r\n...answer...", "type": "answer"}

        async def _fake_post(url, *, json, timeout):  # noqa: ANN001
            assert url.endswith(f"/cameras/{camera_id}/webrtc/offer")
            assert json == TestWebRtcOfferProxy._BODY
            return _FakeResponse()

        app = create_app()
        app.dependency_overrides[get_webrtc_proxy_client] = lambda: _FakeWebRtcProxyClient(
            _fake_post
        )
        async with await _client(app) as client:
            response = await client.post(
                f"/cameras/{camera_id}/webrtc/offer",
                json=self._BODY,
                headers=_auth_header(viewer, ROLE_VIEWER),
            )
        assert response.status_code == 200
        assert response.json()["data"] == {"sdp": "v=0\r\n...answer...", "type": "answer"}

    async def test_unreachable_deepstream_signaling_server_returns_503(
        self, db_engine, db_session
    ) -> None:
        viewer = await _make_user(db_session, ROLE_VIEWER)

        async def _fake_post(url, *, json, timeout):  # noqa: ANN001
            raise httpx.ConnectError("connection refused")

        app = create_app()
        app.dependency_overrides[get_webrtc_proxy_client] = lambda: _FakeWebRtcProxyClient(
            _fake_post
        )
        async with await _client(app) as client:
            response = await client.post(
                f"/cameras/{uuid.uuid4()}/webrtc/offer",
                json=self._BODY,
                headers=_auth_header(viewer, ROLE_VIEWER),
            )
        assert response.status_code == 503

    async def test_unknown_camera_returns_404(self, db_engine, db_session) -> None:
        viewer = await _make_user(db_session, ROLE_VIEWER)

        class _FakeResponse:
            status_code = 404

            def json(self) -> dict:
                return {}

        async def _fake_post(url, *, json, timeout):  # noqa: ANN001
            return _FakeResponse()

        app = create_app()
        app.dependency_overrides[get_webrtc_proxy_client] = lambda: _FakeWebRtcProxyClient(
            _fake_post
        )
        async with await _client(app) as client:
            response = await client.post(
                f"/cameras/{uuid.uuid4()}/webrtc/offer",
                json=self._BODY,
                headers=_auth_header(viewer, ROLE_VIEWER),
            )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestIncidentsPatch:
    async def test_requires_operator_role(self, db_engine, db_session) -> None:
        camera = await _make_camera(db_session)
        incident = await _make_incident(db_session, camera)
        viewer = await _make_user(db_session, ROLE_VIEWER)
        app = create_app()
        async with await _client(app) as client:
            response = await client.patch(
                f"/incidents/{incident.id}",
                json={"status": "ACKNOWLEDGED"},
                headers=_auth_header(viewer, ROLE_VIEWER),
            )
        assert response.status_code == 403

    async def test_operator_transitions_active_to_acknowledged(self, db_engine, db_session) -> None:
        camera = await _make_camera(db_session)
        incident = await _make_incident(db_session, camera)
        operator = await _make_user(db_session, ROLE_OPERATOR)
        app = create_app()
        async with await _client(app) as client:
            response = await client.patch(
                f"/incidents/{incident.id}",
                json={"status": "ACKNOWLEDGED"},
                headers=_auth_header(operator, ROLE_OPERATOR),
            )

        assert response.status_code == 200
        assert response.json()["data"]["status"] == "ACKNOWLEDGED"

        entries = await AuditLogRepository(db_session).list()
        matching = [e for e in entries if e.action == "TRANSITION_INCIDENT"]
        assert len(matching) == 1
        assert matching[0].details == {"old_status": "ACTIVE", "new_status": "ACKNOWLEDGED"}

    async def test_rejects_a_transition_not_externally_requestable(
        self, db_engine, db_session
    ) -> None:
        camera = await _make_camera(db_session)
        incident = await _make_incident(db_session, camera, status=IncidentStatus.NEW)
        operator = await _make_user(db_session, ROLE_OPERATOR)
        app = create_app()
        async with await _client(app) as client:
            response = await client.patch(
                f"/incidents/{incident.id}",
                json={"status": "ACKNOWLEDGED"},
                headers=_auth_header(operator, ROLE_OPERATOR),
            )
        assert response.status_code == 409

    async def test_returns_404_for_missing_incident(self, db_engine, db_session) -> None:
        operator = await _make_user(db_session, ROLE_OPERATOR)
        app = create_app()
        async with await _client(app) as client:
            response = await client.patch(
                "/incidents/00000000-0000-0000-0000-000000000000",
                json={"status": "ACKNOWLEDGED"},
                headers=_auth_header(operator, ROLE_OPERATOR),
            )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestReviewsWriteRoutes:
    async def test_requires_operator_role(self, db_engine, db_session) -> None:
        camera = await _make_camera(db_session)
        item = await _make_review(db_session, camera)
        viewer = await _make_user(db_session, ROLE_VIEWER)
        app = create_app()
        async with await _client(app) as client:
            response = await client.post(
                f"/reviews/{item.id}/dismiss", headers=_auth_header(viewer, ROLE_VIEWER)
            )
        assert response.status_code == 403

    @pytest.mark.parametrize(
        ("route", "expected_status"),
        [
            ("confirm-military", "CONFIRMED_MILITARY"),
            ("confirm-civilian", "CONFIRMED_CIVILIAN"),
            ("escalate", "ESCALATED"),
            ("dismiss", "DISMISSED"),
        ],
    )
    async def test_each_action_resolves_with_the_expected_status(
        self, db_engine, db_session, route: str, expected_status: str
    ) -> None:
        camera = await _make_camera(db_session)
        item = await _make_review(db_session, camera)
        operator = await _make_user(db_session, ROLE_OPERATOR)
        app = create_app()
        async with await _client(app) as client:
            response = await client.post(
                f"/reviews/{item.id}/{route}", headers=_auth_header(operator, ROLE_OPERATOR)
            )

        assert response.status_code == 200
        assert response.json()["data"]["status"] == expected_status

    async def test_patch_resolves_via_the_generic_form(self, db_engine, db_session) -> None:
        camera = await _make_camera(db_session)
        item = await _make_review(db_session, camera)
        operator = await _make_user(db_session, ROLE_OPERATOR)
        app = create_app()
        async with await _client(app) as client:
            response = await client.patch(
                f"/reviews/{item.id}",
                json={"status": "ESCALATED"},
                headers=_auth_header(operator, ROLE_OPERATOR),
            )
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "ESCALATED"

    async def test_resolving_an_already_resolved_item_returns_409(
        self, db_engine, db_session
    ) -> None:
        camera = await _make_camera(db_session)
        item = await _make_review(db_session, camera)
        operator = await _make_user(db_session, ROLE_OPERATOR)
        app = create_app()
        headers = _auth_header(operator, ROLE_OPERATOR)
        async with await _client(app) as client:
            first = await client.post(f"/reviews/{item.id}/dismiss", headers=headers)
            second = await client.post(f"/reviews/{item.id}/dismiss", headers=headers)

        assert first.status_code == 200
        assert second.status_code == 409

    async def test_returns_404_for_missing_review(self, db_engine, db_session) -> None:
        operator = await _make_user(db_session, ROLE_OPERATOR)
        app = create_app()
        async with await _client(app) as client:
            response = await client.post(
                "/reviews/00000000-0000-0000-0000-000000000000/dismiss",
                headers=_auth_header(operator, ROLE_OPERATOR),
            )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestCalibrationWriteRoutes:
    async def test_requires_operator_role(self, db_engine, db_session) -> None:
        camera = await _make_camera(db_session)
        viewer = await _make_user(db_session, ROLE_VIEWER)
        app = create_app()
        async with await _client(app) as client:
            response = await client.post(
                "/calibration/start",
                json={"camera_id": str(camera.id), "reference_points": []},
                headers=_auth_header(viewer, ROLE_VIEWER),
            )
        assert response.status_code == 403

    async def test_start_persists_a_calibration_then_validate_uses_it(
        self, db_engine, db_session
    ) -> None:
        camera = await _make_camera(db_session)
        operator = await _make_user(db_session, ROLE_OPERATOR)
        headers = _auth_header(operator, ROLE_OPERATOR)
        app = create_app()
        async with await _client(app) as client:
            not_found = await client.post(
                "/calibration/validate",
                json={"camera_id": str(camera.id), "image_x": 1.0, "image_y": 2.0},
                headers=headers,
            )
            assert not_found.status_code == 404

            start = await client.post(
                "/calibration/start",
                json={
                    "camera_id": str(camera.id),
                    "reference_points": [
                        {"image_x": 0, "image_y": 0, "ground_x": 0, "ground_y": 0},
                        {"image_x": 10, "image_y": 0, "ground_x": 5, "ground_y": 0},
                        {"image_x": 0, "image_y": 10, "ground_x": 0, "ground_y": 5},
                        {"image_x": 10, "image_y": 10, "ground_x": 5, "ground_y": 5},
                    ],
                },
                headers=headers,
            )
            assert start.status_code == 200

            validate = await client.post(
                "/calibration/validate",
                json={"camera_id": str(camera.id), "image_x": 5.0, "image_y": 5.0},
                headers=headers,
            )

        assert validate.status_code == 200
        assert validate.json()["data"]["zone"] == "zone_1"

        entries = await AuditLogRepository(db_session).list()
        actions = {e.action for e in entries}
        assert "START_CALIBRATION" in actions
        assert "VALIDATE_CALIBRATION" in actions

    async def test_start_rejects_insufficient_reference_points(self, db_engine, db_session) -> None:
        camera = await _make_camera(db_session)
        operator = await _make_user(db_session, ROLE_OPERATOR)
        app = create_app()
        async with await _client(app) as client:
            response = await client.post(
                "/calibration/start",
                json={
                    "camera_id": str(camera.id),
                    "reference_points": [
                        {"image_x": 0, "image_y": 0, "ground_x": 0, "ground_y": 0},
                    ],
                },
                headers=_auth_header(operator, ROLE_OPERATOR),
            )
        assert response.status_code == 422

    async def test_start_returns_404_for_missing_camera(self, db_engine, db_session) -> None:
        operator = await _make_user(db_session, ROLE_OPERATOR)
        app = create_app()
        async with await _client(app) as client:
            response = await client.post(
                "/calibration/start",
                json={
                    "camera_id": "00000000-0000-0000-0000-000000000000",
                    "reference_points": [
                        {"image_x": 0, "image_y": 0, "ground_x": 0, "ground_y": 0},
                        {"image_x": 10, "image_y": 0, "ground_x": 5, "ground_y": 0},
                        {"image_x": 0, "image_y": 10, "ground_x": 0, "ground_y": 5},
                        {"image_x": 10, "image_y": 10, "ground_x": 5, "ground_y": 5},
                    ],
                },
                headers=_auth_header(operator, ROLE_OPERATOR),
            )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestUsersRoutes:
    async def test_list_requires_admin(self, db_engine, db_session) -> None:
        operator = await _make_user(db_session, ROLE_OPERATOR)
        app = create_app()
        async with await _client(app) as client:
            response = await client.get("/users", headers=_auth_header(operator, ROLE_OPERATOR))
        assert response.status_code == 403

    async def test_list_returns_users_without_password_hash(self, db_engine, db_session) -> None:
        admin = await _make_user(db_session, ROLE_ADMIN)
        app = create_app()
        async with await _client(app) as client:
            response = await client.get("/users", headers=_auth_header(admin, ROLE_ADMIN))

        assert response.status_code == 200
        assert len(response.json()["data"]) >= 1
        assert "password_hash" not in response.json()["data"][0]

    async def test_patch_requires_admin(self, db_engine, db_session) -> None:
        operator = await _make_user(db_session, ROLE_OPERATOR)
        target = await _make_user(db_session, ROLE_VIEWER)
        app = create_app()
        async with await _client(app) as client:
            response = await client.patch(
                f"/users/{target.id}",
                json={"role": "admin"},
                headers=_auth_header(operator, ROLE_OPERATOR),
            )
        assert response.status_code == 403

    async def test_admin_updates_a_users_role_and_writes_audit_row(
        self, db_engine, db_session
    ) -> None:
        admin = await _make_user(db_session, ROLE_ADMIN)
        target = await _make_user(db_session, ROLE_VIEWER)
        app = create_app()
        async with await _client(app) as client:
            response = await client.patch(
                f"/users/{target.id}",
                json={"role": "operator"},
                headers=_auth_header(admin, ROLE_ADMIN),
            )

        assert response.status_code == 200
        assert response.json()["data"]["role"] == "operator"

        entries = await AuditLogRepository(db_session).list()
        matching = [e for e in entries if e.action == "UPDATE_USER_ROLE"]
        assert len(matching) == 1
        assert matching[0].details == {"old_role": "viewer", "new_role": "operator"}

    async def test_rejects_an_unrecognized_role(self, db_engine, db_session) -> None:
        admin = await _make_user(db_session, ROLE_ADMIN)
        target = await _make_user(db_session, ROLE_VIEWER)
        app = create_app()
        async with await _client(app) as client:
            response = await client.patch(
                f"/users/{target.id}",
                json={"role": "not-a-real-role"},
                headers=_auth_header(admin, ROLE_ADMIN),
            )
        assert response.status_code == 422

    async def test_returns_404_for_missing_user(self, db_engine, db_session) -> None:
        admin = await _make_user(db_session, ROLE_ADMIN)
        app = create_app()
        async with await _client(app) as client:
            response = await client.patch(
                "/users/00000000-0000-0000-0000-000000000000",
                json={"role": "admin"},
                headers=_auth_header(admin, ROLE_ADMIN),
            )
        assert response.status_code == 404
