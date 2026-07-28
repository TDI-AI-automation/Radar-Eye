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
        call, no event published by this route (only lifecycle changes
        publish an event -- these are plain persisted fields)."""
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


@pytest.mark.asyncio
class TestCamerasPost:
    """Camera Registry -- RM-12. POST /cameras is the fix for the gap the
    RM-12 gap analysis found: no API path to register a camera existed
    before this, only the out-of-band scripts/siv_register_camera.py."""

    _BODY = {
        "name": "gate-cam-1",
        "location": "north gate",
        "rtsp_url": "rtsp://192.0.2.10:554/stream1",
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
        assert data["lifecycle_state"] == "DRAFT"
        # RM-12 Design Principle 3: adding a camera must never auto-start AI;
        # the same default applies symmetrically to recording.
        assert data["ai_enabled"] is False
        assert data["recording_enabled"] is False
        assert "rtsp_url" not in data and "password" not in data

        camera = await CameraRepository(db_session).get(uuid.UUID(data["camera_id"]))
        assert camera is not None
        profiles = await CameraStreamProfileRepository(db_session).list()
        profile = next(p for p in profiles if p.camera_id == camera.id)
        assert profile.transport == "tcp"
        assert "hunter2" not in profile.rtsp_url_encrypted  # genuinely ciphertext, not plaintext

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
class TestCamerasLifecyclePatch:
    """Camera Registry lifecycle transitions -- RM-12 §10's state machine,
    independent of CameraConnectionStatus (Observed state, never touched
    here)."""

    async def test_requires_authentication(self, db_engine, db_session) -> None:
        camera = await _make_camera(db_session, lifecycle_state="DRAFT")
        app = create_app()
        async with await _client(app) as client:
            response = await client.patch(
                f"/cameras/{camera.id}/lifecycle", json={"target_state": "TESTING"}
            )
        assert response.status_code == 401

    async def test_rejects_non_admin(self, db_engine, db_session) -> None:
        camera = await _make_camera(db_session, lifecycle_state="DRAFT")
        operator = await _make_user(db_session, ROLE_OPERATOR)
        app = create_app()
        async with await _client(app) as client:
            response = await client.patch(
                f"/cameras/{camera.id}/lifecycle",
                json={"target_state": "TESTING"},
                headers=_auth_header(operator, ROLE_OPERATOR),
            )
        assert response.status_code == 403

    async def test_valid_transition_updates_state_and_writes_audit_row(
        self, db_engine, db_session
    ) -> None:
        camera = await _make_camera(db_session, lifecycle_state="DRAFT")
        admin = await _make_user(db_session, ROLE_ADMIN)
        app = create_app()
        async with await _client(app) as client:
            response = await client.patch(
                f"/cameras/{camera.id}/lifecycle",
                json={"target_state": "TESTING"},
                headers=_auth_header(admin, ROLE_ADMIN),
            )

        assert response.status_code == 200
        assert response.json()["data"]["lifecycle_state"] == "TESTING"

        entries = await AuditLogRepository(db_session).list()
        matching = [e for e in entries if e.action == "CHANGE_CAMERA_LIFECYCLE"]
        assert len(matching) == 1
        assert matching[0].details == {"previous_state": "DRAFT", "new_state": "TESTING"}

    async def test_invalid_transition_rejected(self, db_engine, db_session) -> None:
        camera = await _make_camera(db_session, lifecycle_state="DRAFT")
        admin = await _make_user(db_session, ROLE_ADMIN)
        app = create_app()
        async with await _client(app) as client:
            # DRAFT -> OPERATIONAL skips TESTING/VERIFIED -- not a legal edge
            # in RM-12 §10's state machine.
            response = await client.patch(
                f"/cameras/{camera.id}/lifecycle",
                json={"target_state": "OPERATIONAL"},
                headers=_auth_header(admin, ROLE_ADMIN),
            )
        assert response.status_code == 422

    async def test_idempotent_same_state_is_a_no_op(self, db_engine, db_session) -> None:
        camera = await _make_camera(db_session, lifecycle_state="TESTING")
        admin = await _make_user(db_session, ROLE_ADMIN)
        app = create_app()
        async with await _client(app) as client:
            response = await client.patch(
                f"/cameras/{camera.id}/lifecycle",
                json={"target_state": "TESTING"},
                headers=_auth_header(admin, ROLE_ADMIN),
            )

        assert response.status_code == 200
        assert response.json()["data"]["lifecycle_state"] == "TESTING"
        entries = await AuditLogRepository(db_session).list()
        assert [e for e in entries if e.action == "CHANGE_CAMERA_LIFECYCLE"] == []

    async def test_returns_404_for_missing_camera(self, db_engine, db_session) -> None:
        admin = await _make_user(db_session, ROLE_ADMIN)
        app = create_app()
        async with await _client(app) as client:
            response = await client.patch(
                "/cameras/00000000-0000-0000-0000-000000000000/lifecycle",
                json={"target_state": "TESTING"},
                headers=_auth_header(admin, ROLE_ADMIN),
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
