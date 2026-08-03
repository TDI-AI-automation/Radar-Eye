"""Camera Management REST router -- RM-12 Phase 3 (reads) + Phase 4 (write)
+ Camera Registry implementation (RM-12 architecture freeze) + the Camera
Management operator workflow (register/edit/delete without curl).

Source: docs/FRONTEND_BACKEND_CONTRACTS.md — Camera Management section,
extended per RM-12's Bounded Contexts / Camera Runtime Ownership
Refinement.
  - GET /cameras
  - GET /cameras/brands
  - GET /cameras/{camera_id}
  - GET /cameras/{camera_id}/calibration
  - PATCH /cameras/{camera_id} (Phase 4, admin-only, audit-logged)
  - POST /cameras (Camera Registry, admin-only, audit-logged)
  - DELETE /cameras/{camera_id} (admin-only, audit-logged)

``GET /cameras/{camera_id}/health`` already exists (RM-09, routers/health.py)
-- not touched here. ``PATCH /cameras/{camera_id}`` never touches ``status``
(Observed state, Camera Runtime's exclusively -- RM-12); it does now touch
``camera_stream_profiles`` for whichever connection fields are present,
via ``CameraRegistryService.update_connection()``.

A registered camera has exactly two operator controls: AI Enable/Disable
(``ai_enabled``, this router) and Connect/Disconnect, which is implicit
in registration/deletion, not a separate state -- there is no Lifecycle
state machine to PATCH.

Every read route requires a valid access token (any authenticated role) per
docs/RM-12_IMPLEMENTATION_PLAN.md Phase 3 -- no per-route role gate; every
write route additionally requires the ``admin`` role, matching the existing
PATCH route's precedent (camera registration is at least as sensitive as
a name/location edit).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.audit import AuditLogger
from apps.api.app.config import LiveStreamProxySettings, Settings, get_live_stream_proxy_settings
from apps.api.app.models.camera import Camera, CameraCalibration, CameraStreamProfile
from apps.api.app.models.user import ROLE_ADMIN
from apps.api.app.repositories.camera import (
    CameraCalibrationRepository,
    CameraRepository,
    CameraStreamProfileRepository,
)
from apps.api.app.security.auth import DecodedToken
from apps.api.app.security.dependencies import (
    get_audit_logger,
    get_current_user,
    get_db_session,
    get_event_bus,
    get_settings,
    require_role,
)
from apps.api.app.security.encryption import get_credential_encryption_provider
from apps.api.app.services.camera_registry import CameraNameConflictError, CameraRegistryService
from apps.api.app.services.rtsp_url_generator import (
    brand_label,
    default_port_for_brand,
    default_stream_path_for_brand,
    supported_brands,
)
from shared.events.bus import EventBus
from shared.schemas.api import ApiResponse
from shared.schemas.camera import (
    CameraBrandInfoSchema,
    CameraCalibrationSchema,
    CameraCreateRequestSchema,
    CameraSchema,
    CameraUpdateRequestSchema,
    WebRtcAnswerResponseSchema,
    WebRtcOfferRequestSchema,
)

router = APIRouter(tags=["Camera Management"], dependencies=[Depends(get_current_user)])

_CONNECTION_FIELDS = frozenset(
    {"brand", "model", "ip_address", "port", "username", "password", "transport", "stream_path"}
)
"""CameraUpdateRequestSchema fields that live on camera_stream_profiles,
not cameras -- routed to CameraRegistryService.update_connection() instead
of the plain setattr loop the rest of the body still uses."""


def _to_camera_schema(camera: Camera, profile: CameraStreamProfile | None) -> CameraSchema:
    return CameraSchema(
        camera_id=camera.id,
        name=camera.name,
        location=camera.location,
        status=camera.status,  # type: ignore[arg-type]
        ai_enabled=camera.ai_enabled,
        recording_enabled=camera.recording_enabled,
        brand=profile.brand if profile is not None else None,  # type: ignore[arg-type]
        model=profile.model if profile is not None else None,
        ip_address=profile.ip_address if profile is not None else None,
        port=profile.port if profile is not None else None,
        stream_path=profile.stream_path if profile is not None else None,
        username=profile.username if profile is not None else None,
        transport=profile.transport if profile is not None else None,
        created_at=camera.created_at,
        updated_at=camera.updated_at,
    )


def _to_calibration_schema(calibration: CameraCalibration) -> CameraCalibrationSchema:
    return CameraCalibrationSchema(
        calibration_id=calibration.id,
        camera_id=calibration.camera_id,
        homography_matrix=calibration.homography_matrix,
        reference_points=calibration.reference_points,
        calibrated_by=calibration.calibrated_by,
        created_at=calibration.created_at,
    )


@router.get("/cameras", response_model=ApiResponse[list[CameraSchema]])
async def list_cameras(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[list[CameraSchema]]:
    cameras = await CameraRepository(session).list()
    profiles = await CameraStreamProfileRepository(session).list()
    profile_by_camera_id = {p.camera_id: p for p in profiles}
    return ApiResponse(
        success=True,
        data=[_to_camera_schema(c, profile_by_camera_id.get(c.id)) for c in cameras],
    )


@router.get("/cameras/brands", response_model=ApiResponse[list[CameraBrandInfoSchema]])
async def list_camera_brands() -> ApiResponse[list[CameraBrandInfoSchema]]:
    """The Add/Edit Camera form's only source of brand choices and
    defaults -- see CameraBrandInfoSchema's own docstring for why this
    exists (so the frontend never hardcodes a second copy of what
    apps.api.app.services.rtsp_url_generator already knows)."""
    return ApiResponse(
        success=True,
        data=[
            CameraBrandInfoSchema(
                brand=brand,
                label=brand_label(brand),
                default_port=default_port_for_brand(brand),
                default_stream_path=default_stream_path_for_brand(brand),
            )
            for brand in supported_brands()
        ],
    )


@router.get("/cameras/{camera_id}", response_model=ApiResponse[CameraSchema])
async def get_camera(
    camera_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[CameraSchema]:
    camera = await CameraRepository(session).get(camera_id)
    if camera is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Camera not found")
    profile = await CameraStreamProfileRepository(session).get_by_camera_id(camera_id)
    return ApiResponse(success=True, data=_to_camera_schema(camera, profile))


@router.get(
    "/cameras/{camera_id}/calibration",
    response_model=ApiResponse[CameraCalibrationSchema],
)
async def get_camera_calibration(
    camera_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiResponse[CameraCalibrationSchema]:
    calibration = await CameraCalibrationRepository(session).get_latest_for_camera(camera_id)
    if calibration is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No calibration recorded for this camera")
    return ApiResponse(success=True, data=_to_calibration_schema(calibration))


@router.post("/cameras", response_model=ApiResponse[CameraSchema])
async def register_camera(
    body: CameraCreateRequestSchema,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    audit_logger: Annotated[AuditLogger, Depends(get_audit_logger)],
    settings: Annotated[Settings, Depends(get_settings)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
    user: Annotated[DecodedToken, Depends(require_role(ROLE_ADMIN))],
) -> ApiResponse[CameraSchema]:
    service = CameraRegistryService(session, get_credential_encryption_provider(settings), bus)
    try:
        camera = await service.register(
            name=body.name,
            location=body.location,
            brand=body.brand,
            model=body.model,
            ip_address=body.ip_address,
            port=body.port,
            stream_path=body.stream_path,
            username=body.username,
            password=body.password,
            transport=body.transport,
            ai_enabled=body.ai_enabled,
            recording_enabled=body.recording_enabled,
        )
    except CameraNameConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    await audit_logger.record(
        session,
        actor_user_id=user.user_id,
        action="REGISTER_CAMERA",
        resource_type="camera",
        resource_id=str(camera.id),
        details={"name": camera.name, "brand": body.brand, "ip_address": body.ip_address},
    )
    profile = await CameraStreamProfileRepository(session).get_by_camera_id(camera.id)
    response_data = _to_camera_schema(camera, profile)
    await session.commit()
    return ApiResponse(success=True, data=response_data)


@router.patch("/cameras/{camera_id}", response_model=ApiResponse[CameraSchema])
async def update_camera(
    camera_id: uuid.UUID,
    body: CameraUpdateRequestSchema,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    audit_logger: Annotated[AuditLogger, Depends(get_audit_logger)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[DecodedToken, Depends(require_role(ROLE_ADMIN))],
) -> ApiResponse[CameraSchema]:
    camera = await CameraRepository(session).get(camera_id)
    if camera is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Camera not found")

    updates = body.model_dump(exclude_unset=True)
    camera_updates = {k: v for k, v in updates.items() if k not in _CONNECTION_FIELDS}
    connection_updates = {k: v for k, v in updates.items() if k in _CONNECTION_FIELDS}

    for field, value in camera_updates.items():
        setattr(camera, field, value)
    if connection_updates:
        service = CameraRegistryService(session, get_credential_encryption_provider(settings))
        await service.update_connection(camera_id, **connection_updates)
    await session.flush()
    # updated_at is server-computed (onupdate=func.now()) -- unlike a
    # server_default populated via RETURNING on INSERT, an UPDATE's
    # onupdate value is not auto-refreshed into the Python object; an
    # explicit refresh() is required before it can be read back.
    await session.refresh(camera)

    # password is write-only and must never reach the audit trail even as
    # "a password was changed" metadata beyond a boolean -- the log entry
    # records that a change happened, never the value.
    audit_details: dict[str, object] = dict(camera_updates)
    if connection_updates:
        audit_details["connection_fields_changed"] = sorted(
            k for k in connection_updates if k != "password"
        )
        if "password" in connection_updates:
            audit_details["password_changed"] = True
    await audit_logger.record(
        session,
        actor_user_id=user.user_id,
        action="UPDATE_CAMERA",
        resource_type="camera",
        resource_id=str(camera.id),
        details=audit_details,
    )
    # Build the response before commit() -- commit() expires ORM attributes
    # by default (expire_on_commit), and a post-commit attribute access
    # would trigger an implicit lazy-load outside the request's async
    # context (MissingGreenlet).
    profile = await CameraStreamProfileRepository(session).get_by_camera_id(camera.id)
    response_data = _to_camera_schema(camera, profile)
    await session.commit()
    return ApiResponse(success=True, data=response_data)


@router.delete("/cameras/{camera_id}", response_model=ApiResponse[None])
async def delete_camera(
    camera_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    audit_logger: Annotated[AuditLogger, Depends(get_audit_logger)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[DecodedToken, Depends(require_role(ROLE_ADMIN))],
) -> ApiResponse[None]:
    camera = await CameraRepository(session).get(camera_id)
    if camera is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Camera not found")

    name = camera.name
    service = CameraRegistryService(session, get_credential_encryption_provider(settings))
    try:
        await service.delete(camera)
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Cannot delete a camera with existing incidents, review items, or recordings -- "
            "that history must be resolved or exported first.",
        ) from exc

    await audit_logger.record(
        session,
        actor_user_id=user.user_id,
        action="DELETE_CAMERA",
        resource_type="camera",
        resource_id=str(camera_id),
        details={"name": name},
    )
    await session.commit()
    return ApiResponse(success=True, data=None)


async def get_webrtc_proxy_client() -> AsyncIterator[httpx.AsyncClient]:
    """Isolated from the test client's own ``httpx.AsyncClient`` usage via
    FastAPI's dependency-override mechanism (``app.dependency_overrides``)
    rather than monkeypatching ``httpx.AsyncClient.post`` globally -- the
    latter would also intercept the test's own calls into this app."""
    async with httpx.AsyncClient() as client:
        yield client


@router.post(
    "/cameras/{camera_id}/webrtc/offer",
    response_model=ApiResponse[WebRtcAnswerResponseSchema],
)
async def post_webrtc_offer(
    camera_id: uuid.UUID,
    body: WebRtcOfferRequestSchema,
    live_stream_settings: Annotated[
        LiveStreamProxySettings, Depends(get_live_stream_proxy_settings)
    ],
    http_client: Annotated[httpx.AsyncClient, Depends(get_webrtc_proxy_client)],
) -> ApiResponse[WebRtcAnswerResponseSchema]:
    """Live Monitoring's video signaling -- proxies the SDP offer/answer
    exchange to apps.deepstream's local-only (127.0.0.1) signaling
    server. This is the one point where the operator's browser reaches
    Live Monitoring's video path; the actual media (once negotiated)
    flows directly between the browser and apps.deepstream over WebRTC,
    not through this route (see apps.deepstream.app.live_stream's module
    docstring). Gated by the router-level ``get_current_user`` dependency
    like every other route here -- ADR-011's "centralized access
    control" applied to signaling, same as everything else in this file.
    """
    url = (
        f"http://{live_stream_settings.host}:{live_stream_settings.port}"
        f"/cameras/{camera_id}/webrtc/offer"
    )
    try:
        response = await http_client.post(url, json=body.model_dump(), timeout=15.0)
    except httpx.RequestError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Live Monitoring's video service is unavailable",
        ) from exc

    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Camera not connected to Live Monitoring")
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Failed to negotiate WebRTC stream")

    return ApiResponse(success=True, data=WebRtcAnswerResponseSchema(**response.json()))
