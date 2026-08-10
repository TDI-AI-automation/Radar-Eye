"""Tests for camera_yaml.py -- shared by siv_register_camera.py and check_rtsp.py."""

from __future__ import annotations

import pytest

from apps.deepstream.app.camera_yaml import CameraYamlError, build_rtsp_url, require_keys


class TestBuildRtspUrl:
    def test_embeds_credentials_when_both_present(self) -> None:
        url = build_rtsp_url(
            {"rtsp_url": "rtsp://192.168.1.50:554/stream1", "username": "op", "password": "pw"}
        )
        assert url == "rtsp://op:pw@192.168.1.50:554/stream1"

    def test_no_credentials_returns_url_unchanged(self) -> None:
        url = build_rtsp_url({"rtsp_url": "rtsp://192.168.1.50:554/stream1"})
        assert url == "rtsp://192.168.1.50:554/stream1"

    def test_partial_credentials_returns_url_unchanged(self) -> None:
        url = build_rtsp_url({"rtsp_url": "rtsp://192.168.1.50:554/stream1", "username": "op"})
        assert url == "rtsp://192.168.1.50:554/stream1"

    def test_already_embedded_credentials_not_duplicated(self) -> None:
        url = build_rtsp_url(
            {
                "rtsp_url": "rtsp://existing:creds@192.168.1.50:554/stream1",
                "username": "op",
                "password": "pw",
            }
        )
        assert url == "rtsp://existing:creds@192.168.1.50:554/stream1"

    def test_missing_rtsp_url_raises(self) -> None:
        with pytest.raises(CameraYamlError, match="rtsp_url"):
            build_rtsp_url({"camera_id": "cam-1"})


class TestRequireKeys:
    def test_passes_when_all_present(self) -> None:
        require_keys({"camera_id": "cam-1", "rtsp_url": "rtsp://x"})  # must not raise

    def test_raises_naming_missing_keys(self) -> None:
        with pytest.raises(CameraYamlError, match="camera_id"):
            require_keys({"rtsp_url": "rtsp://x"})
