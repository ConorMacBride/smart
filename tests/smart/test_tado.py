from pathlib import Path
from unittest.mock import patch, PropertyMock

import pytest

from smart.tado import TadoClient


class HttpResponse:
    def __init__(self, json=None):
        self._json = json

    def json(self):
        return self._json

    def raise_for_status(self):
        return


class TestTado:
    def test_setup_tado_client(self, tado_client):
        assert tado_client.username == "username"
        assert tado_client.password == "password"
        assert tado_client.data == Path(".")
        assert tado_client.env == "http://localhost:8080/webapp/env.js"
        assert tado_client.oauth_endpoint == "http://localhost:8080/oauth"
        assert tado_client.client_id == "client-id"
        assert tado_client.client_secret == "client-secret"
        assert tado_client.v1_endpoint == "http://localhost:8080/api/v1"
        assert tado_client.v2_endpoint == "http://localhost:8080/api/v2"

    def test_default_env(self):
        with patch("smart.tado.TadoClient._env", new_callable=PropertyMock) as mock_env:
            with (Path(__file__).parent.parent / "mock_env.txt").open() as fp:
                mock_env.return_value = fp.read().strip()
            tado_client = TadoClient(
                username="username",
                password="password",
                data=".",
            )
            assert tado_client.env == "https://my.tado.com/webapp/env.js"

    def test_get_env(self, tado_client):
        with patch("smart.tado.TadoClient._env", new_callable=PropertyMock) as mock_env:
            mock_env.return_value = "varA: 'val1',\nvarB: 'val2',\nvarC: 'val3',\nvarE: 'val5',\nvarE: 'val6',"

            assert tado_client.get_env("varA") == "val1"
            assert tado_client.get_env("varB") == "val2"
            assert tado_client.get_env("varC") == "val3"

            assert tado_client.get_env("varC", "val0") == "val3"
            assert tado_client.get_env("varD", "val4") == "val4"

            with pytest.raises(ValueError, match="not in environment"):
                tado_client.get_env("varD")

            with pytest.raises(ValueError, match="Multiple"):
                tado_client.get_env("varE")

            with pytest.raises(ValueError, match="Multiple"):
                tado_client.get_env("varE", "val7")

    def test_auth(self, tado_client):
        tado_client.requests_session.post.return_value = HttpResponse(
            json={"access_token": "access-token"}
        )
        assert tado_client.auth == {"Authorization": "Bearer access-token"}
        assert tado_client.access_token == "access-token"
        tado_client.requests_session.post.assert_called_once_with(
            "http://localhost:8080/oauth/token",
            data={
                "client_id": "client-id",
                "grant_type": "password",
                "scope": "home.user",
                "username": "username",
                "password": "password",
                "client_secret": "client-secret",
            },
        )

    def test_home_id(self, tado_client, mock_tado_auth):
        tado_client.requests_session.get.return_value = HttpResponse(
            json={"homeId": "123"}
        )
        assert tado_client.home_id == "123"
        tado_client.requests_session.get.assert_called_once_with(
            "http://localhost:8080/api/v1/me",
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
