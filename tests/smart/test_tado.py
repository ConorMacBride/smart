import logging
import time
from pathlib import Path
from unittest.mock import call

import pytest

from smart.tado import TadoClient
from tests.conftest import create_tado_client


class HttpResponse:
    def __init__(self, json=None, status_code=200):
        self._json = json
        self.status_code = status_code

    def json(self):
        return self._json

    def raise_for_status(self):
        return


class TestTado:
    def test_setup_tado_client(self, tado_client):
        assert tado_client.data == Path(".")
        assert tado_client.oauth2_endpoint == "http://localhost:8080/oauth2"
        assert tado_client.client_id == "1bb50063-6b0c-4d11-bd99-387f4a91cc46"
        assert tado_client.v2_endpoint == "http://localhost:8080/api/v2"

    def test_default_env(self):
        tado_client = TadoClient(data=".")
        assert tado_client.v2_endpoint == "https://my.tado.com/api/v2"
        assert tado_client.oauth2_endpoint == "https://login.tado.com/oauth2"

    def test_auth(self, tado_client, tmp_path, caplog):
        tado_client.data = tmp_path / "data1"
        tado_client.data.mkdir()
        call_count = {"count": 0}

        def mock_post(url, *args, **kwargs):
            if url.endswith("/oauth2/device_authorize"):
                return HttpResponse(
                    json={
                        "device_code": "my-new-device",
                        "expires_in": 1,
                        "interval": 0,
                        "user_code": "",
                        "verification_uri": "",
                        "verification_uri_complete": "https://example.com/verify/1234",
                    }
                )
            else:
                assert url.endswith("/oauth2/token")
                if call_count["count"] < 2:
                    call_count["count"] += 1
                    return HttpResponse(status_code=403)
                return HttpResponse(
                    json={
                        "access_token": "access-token",
                        "expires_in": 61,
                        "refresh_token": "xxx",
                        "scope": "offline_access",
                        "token_type": "bearer",
                        "userId": "Conor",
                    }
                )

        tado_client.requests_session.post.side_effect = mock_post

        with caplog.at_level(logging.INFO):
            assert tado_client.token.access_token == "access-token"
        assert "https://example.com/verify/1234" in caplog.text
        assert (tado_client.data / "token.json").stat().st_mode & 0o777 == 0o600
        assert tado_client.token.access_token == "access-token"

        time.sleep(1)
        assert tado_client.token.access_token == "access-token"
        assert tado_client.token.access_token == "access-token"

        time.sleep(1)
        assert tado_client.token.access_token == "access-token"
        assert tado_client.auth == {"Authorization": "Bearer access-token"}
        expires_in = tado_client.token.expires_in

        tado_client.requests_session.post.assert_has_calls(
            [
                call(
                    "http://localhost:8080/oauth2/device_authorize",
                    data={
                        "client_id": "1bb50063-6b0c-4d11-bd99-387f4a91cc46",
                        "scope": "offline_access",
                    },
                ),
                call(
                    "http://localhost:8080/oauth2/token",
                    data={
                        "client_id": "1bb50063-6b0c-4d11-bd99-387f4a91cc46",
                        "device_code": "my-new-device",
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    },
                ),
                call(
                    "http://localhost:8080/oauth2/token",
                    data={
                        "client_id": "1bb50063-6b0c-4d11-bd99-387f4a91cc46",
                        "device_code": "my-new-device",
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    },
                ),
                call(
                    "http://localhost:8080/oauth2/token",
                    data={
                        "client_id": "1bb50063-6b0c-4d11-bd99-387f4a91cc46",
                        "device_code": "my-new-device",
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    },
                ),
                call(
                    "http://localhost:8080/oauth2/token",
                    data={
                        "client_id": "1bb50063-6b0c-4d11-bd99-387f4a91cc46",
                        "grant_type": "refresh_token",
                        "refresh_token": "xxx",
                    },
                ),
                call(
                    "http://localhost:8080/oauth2/token",
                    data={
                        "client_id": "1bb50063-6b0c-4d11-bd99-387f4a91cc46",
                        "grant_type": "refresh_token",
                        "refresh_token": "xxx",
                    },
                ),
            ]
        )

        new_client = create_tado_client()
        new_client.data = tmp_path / "data2"
        new_client.data.mkdir()
        src = tado_client.data / "token.json"
        dst = new_client.data / "token.json"
        dst.write_text(src.read_text())
        assert new_client.token.expires_in == expires_in
        assert new_client.token.access_token == "access-token"

    def test_auth_timeout(self, tado_client, tmp_path, caplog):
        tado_client.data = tmp_path

        def mock_post(url, *args, **kwargs):
            if url.endswith("/oauth2/device_authorize"):
                return HttpResponse(
                    json={
                        "device_code": "my-new-device",
                        "expires_in": 1,
                        "interval": 0,
                        "user_code": "",
                        "verification_uri": "",
                        "verification_uri_complete": "https://example.com/verify/1234",
                    }
                )
            else:
                assert url.endswith("/oauth2/token")
                return HttpResponse(status_code=403)

        tado_client.requests_session.post.side_effect = mock_post
        with pytest.raises(TimeoutError), caplog.at_level(logging.INFO):
            _ = tado_client.token
        assert "https://example.com/verify/1234" in caplog.text
        assert not (tado_client.data / "token.json").exists()

    def test_home_id(self, tado_client, mock_tado_auth):
        tado_client.requests_session.get.return_value = HttpResponse(
            json={"homes": [{"id": "123"}]}
        )
        assert tado_client.home_id == "123"
        tado_client.requests_session.get.assert_called_once_with(
            "http://localhost:8080/api/v2/me",
            headers={"Authorization": "Bearer access-token"},
        )

    def test_zones(self, tado_client, mock_tado_auth, mock_tado_home_id):
        zones = [
            {"id": 1, "name": "Dining Room", "type": "HEATING"},
            {"id": 2, "name": "Bathroom", "type": "HEATING"},
            {"id": 3, "name": "Living Room", "type": "HEATING"},
        ]
        tado_client.requests_session.get.return_value = HttpResponse(json=zones)
        assert tado_client.zones == zones
        tado_client.requests_session.get.assert_called_once_with(
            "http://localhost:8080/api/v2/homes/123/zones",
            headers={"Authorization": "Bearer access-token"},
        )

    def test_set_home(self, tado_client, mock_tado_auth, mock_tado_home_id):
        tado_client.set_home()
        tado_client.requests_session.put.assert_called_once_with(
            "http://localhost:8080/api/v2/homes/123/presenceLock",
            json={"homePresence": "HOME"},
            headers={"Authorization": "Bearer access-token"},
        )

    def test_set_away(self, tado_client, mock_tado_auth, mock_tado_home_id):
        tado_client.set_away()
        tado_client.requests_session.put.assert_called_once_with(
            "http://localhost:8080/api/v2/homes/123/presenceLock",
            json={"homePresence": "AWAY"},
            headers={"Authorization": "Bearer access-token"},
        )

    def test_get_presence(self, tado_client, mock_tado_auth, mock_tado_home_id):
        tado_client.requests_session.get.return_value = HttpResponse(
            json={"presence": "HERE"}
        )
        assert tado_client.get_presence() == "HERE"
        tado_client.requests_session.get.assert_called_once_with(
            "http://localhost:8080/api/v2/homes/123/state",
            headers={"Authorization": "Bearer access-token"},
        )
