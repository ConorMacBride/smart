import re
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Optional, Iterator
from unittest.mock import patch

import pytest
import responses
from fastapi.testclient import TestClient
from pydantic_settings import BaseSettings

from app.main import app
from smart import __version__


class Settings(BaseSettings):
    api_key: str = "test_api_key"
    tado_username: str = "test_username"
    tado_password: str = "test_password"
    tado_data: str = tempfile.mkdtemp()
    tado_default_schedule: str = "Schedule 2"
    tado_env: Optional[str] = "http://localhost:8080/webapp/env.js"


@lru_cache
def get_test_settings():
    return Settings()


@pytest.fixture(scope="session", autouse=True)
def default_session_fixture() -> Iterator[None]:
    with patch("app.main.get_settings", get_test_settings):
        yield


client = TestClient(app, headers={"x-api-key": "test_api_key"})

auth_resp = {
    "method": responses.GET,
    "url": "http://localhost:8080/webapp/env.js",
    "body": (Path(__file__).parent / "mock_env.js").read_text(),
}

token_resp = {
    "method": responses.POST,
    "url": "http://localhost:8080/oauth/token",
    "match": (
        responses.matchers.urlencoded_params_matcher(
            {
                "client_id": "test-web-app",
                "grant_type": "password",
                "scope": "home.user",
                "username": "test_username",
                "password": "test_password",
                "client_secret": "client-secret",
            }
        ),
    ),
    "json": {"access_token": "access-token"},
}

home_id_resp = {
    "method": responses.GET,
    "url": "http://localhost:8081/api/v1/me",
    "headers": {"Authorization": "Bearer access-token"},
    "json": {"homeId": "123"},
}

zones_resp = {
    "method": responses.GET,
    "url": "http://localhost:8081/api/v2/homes/123/zones",
    "headers": {"Authorization": "Bearer access-token"},
    "json": [
        {"id": 1, "name": "Dining Room", "type": "HEATING"},
        {"id": 2, "name": "Bathroom", "type": "HEATING"},
        {"id": 3, "name": "Living Room", "type": "HEATING"},
    ],
}

active_timetable_resp = {
    "method": responses.GET,
    "url": re.compile(
        r"http://localhost:8081/api/v2/homes/123/zones/(1|2|3)/schedule/activeTimetable"
    ),
    "headers": {"Authorization": "Bearer access-token"},
    "json": {"id": 0, "type": "ONE_DAY"},
}


def setup_module():
    temp_dir = Path(get_test_settings().tado_data) / "schedules"
    temp_dir.mkdir()
    for i in range(1, 4):
        src = Path(__file__).parent / f"../sample_schedule_{i}.toml"
        dst = temp_dir / f"sample_schedule_{i}.toml"
        dst.write_text(src.read_text())


class CommonTests:
    def test_missing_api_key(self):
        response = client.get("/", headers={"x-api-key": ""})
        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid or missing API Key"}
        assert response.headers["content-type"] == "application/json"

    def test_invalid_api_key(self):
        response = client.get("/", headers={"x-api-key": "invalid"})
        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid or missing API Key"}
        assert response.headers["content-type"] == "application/json"


class TestRoot(CommonTests):
    @responses.activate(assert_all_requests_are_fired=True)
    def test_get(self):
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == {"version": __version__}
        assert response.headers["content-type"] == "application/json"


class TestHome(CommonTests):
    @responses.activate(assert_all_requests_are_fired=True)
    def test_get(self):
        responses.add(**auth_resp)
        responses.add(**token_resp)
        responses.add(**home_id_resp)
        responses.add(
            method=responses.PUT,
            url="http://localhost:8081/api/v2/homes/123/presenceLock",
            headers={"Authorization": "Bearer access-token"},
            match=(responses.matchers.json_params_matcher({"homePresence": "HOME"}),),
        )
        responses.add(
            method=responses.GET,
            url="http://localhost:8081/api/v2/homes/123/state",
            headers={"Authorization": "Bearer access-token"},
            json={"presence": "HOME"},
        )
        response = client.get("/tado/home")
        assert response.status_code == 200

    @responses.activate(assert_all_requests_are_fired=True)
    def test_get_did_not_update_state(self):
        responses.add(**auth_resp)
        responses.add(**token_resp)
        responses.add(**home_id_resp)
        responses.add(
            method=responses.PUT,
            url="http://localhost:8081/api/v2/homes/123/presenceLock",
            headers={"Authorization": "Bearer access-token"},
            match=(responses.matchers.json_params_matcher({"homePresence": "HOME"}),),
        )
        responses.add(
            method=responses.GET,
            url="http://localhost:8081/api/v2/homes/123/state",
            headers={"Authorization": "Bearer access-token"},
            json={"presence": "AWAY"},
        )
        response = client.get("/tado/home")
        assert response.status_code == 500


class TestAway(CommonTests):
    @responses.activate(assert_all_requests_are_fired=True)
    def test_get(self):
        responses.add(**auth_resp)
        responses.add(**token_resp)
        responses.add(**home_id_resp)
        responses.add(
            method=responses.PUT,
            url="http://localhost:8081/api/v2/homes/123/presenceLock",
            headers={"Authorization": "Bearer access-token"},
            match=(responses.matchers.json_params_matcher({"homePresence": "AWAY"}),),
        )
        responses.add(
            method=responses.GET,
            url="http://localhost:8081/api/v2/homes/123/state",
            headers={"Authorization": "Bearer access-token"},
            json={"presence": "AWAY"},
        )
        response = client.get("/tado/away")
        assert response.status_code == 200

    @responses.activate(assert_all_requests_are_fired=True)
    def test_get_did_not_update_state(self):
        responses.add(**auth_resp)
        responses.add(**token_resp)
        responses.add(**home_id_resp)
        responses.add(
            method=responses.PUT,
            url="http://localhost:8081/api/v2/homes/123/presenceLock",
            headers={"Authorization": "Bearer access-token"},
            match=(responses.matchers.json_params_matcher({"homePresence": "AWAY"}),),
        )
        responses.add(
            method=responses.GET,
            url="http://localhost:8081/api/v2/homes/123/state",
            headers={"Authorization": "Bearer access-token"},
            json={"presence": "HOME"},
        )
        response = client.get("/tado/away")
        assert response.status_code == 500


class TestScheduleReset(CommonTests):
    @responses.activate(assert_all_requests_are_fired=True)
    def test_get(self):
        responses.add(**auth_resp)
        responses.add(**token_resp)
        responses.add(**home_id_resp)
        responses.add(**zones_resp)
        responses.add(**active_timetable_resp)
        responses.add(**active_timetable_resp)
        responses.add(**active_timetable_resp)
        responses.add(
            method=responses.PUT,
            url="http://localhost:8081/api/v2/homes/123/zones/1/schedule/timetables/0/blocks/MONDAY_TO_SUNDAY",
            headers={"Authorization": "Bearer access-token"},
            match=(
                responses.matchers.json_params_matcher(
                    [
                        {
                            "dayType": "MONDAY_TO_SUNDAY",
                            "start": "00:00",
                            "end": "09:00",
                            "geolocationOverride": False,
                            "setting": {
                                "type": "HEATING",
                                "power": "OFF",
                                "temperature": None,
                            },
                        },
                        {
                            "dayType": "MONDAY_TO_SUNDAY",
                            "start": "09:00",
                            "end": "10:00",
                            "geolocationOverride": False,
                            "setting": {
                                "type": "HEATING",
                                "power": "ON",
                                "temperature": {"celsius": 21, "fahrenheit": 69.8},
                            },
                        },
                        {
                            "dayType": "MONDAY_TO_SUNDAY",
                            "start": "10:00",
                            "end": "17:00",
                            "geolocationOverride": False,
                            "setting": {
                                "type": "HEATING",
                                "power": "ON",
                                "temperature": {"celsius": 17.5, "fahrenheit": 63.5},
                            },
                        },
                        {
                            "dayType": "MONDAY_TO_SUNDAY",
                            "start": "17:00",
                            "end": "23:15",
                            "geolocationOverride": False,
                            "setting": {
                                "type": "HEATING",
                                "power": "ON",
                                "temperature": {"celsius": 22.5, "fahrenheit": 72.5},
                            },
                        },
                        {
                            "dayType": "MONDAY_TO_SUNDAY",
                            "start": "23:15",
                            "end": "00:00",
                            "geolocationOverride": False,
                            "setting": {
                                "type": "HEATING",
                                "power": "OFF",
                                "temperature": None,
                            },
                        },
                    ]
                ),
            ),
        )
        responses.add(
            method=responses.PUT,
            url="http://localhost:8081/api/v2/homes/123/zones/2/schedule/timetables/0/blocks/MONDAY_TO_SUNDAY",
            headers={"Authorization": "Bearer access-token"},
        )
        responses.add(
            method=responses.PUT,
            url="http://localhost:8081/api/v2/homes/123/zones/3/schedule/timetables/0/blocks/MONDAY_TO_SUNDAY",
            headers={"Authorization": "Bearer access-token"},
        )
        response = client.get("/tado/schedule/reset")
        assert response.status_code == 200


class TestScheduleActive(CommonTests):
    @responses.activate(assert_all_requests_are_fired=True)
    def test_get(self):
        (Path(get_test_settings().tado_data) / "active_schedule.json").write_text(
            '{"schedule": "My Schedule", "variables": {"var1": "value1"}}'
        )
        responses.add(**auth_resp)
        responses.add(**token_resp)
        responses.add(**home_id_resp)
        responses.add(**zones_resp)
        response = client.get("/tado/schedule/active")
        assert response.status_code == 200
        assert response.json() == {
            "schedule": "My Schedule",
            "variables": {"var1": "value1"},
        }
        assert response.headers["content-type"] == "application/json"


class TestScheduleAll(CommonTests):
    @responses.activate(assert_all_requests_are_fired=True)
    def test_get(self):
        responses.add(**auth_resp)
        response = client.get("/tado/schedule/all")
        assert response.status_code == 200
        assert response.json() == {
            "Schedule 1": {},
            "Schedule 2": {"var1": "09:00", "var2": "10:00"},
            "Schedule 3": {"var1": "09:00", "var2": "10:00"},
            "Schedule 3.1": {"var1": "09:30", "var2": "10:00"},
            "Schedule 3.2": {"var1": "09:00", "var2": "09:30"},
        }
        assert response.headers["content-type"] == "application/json"


class TestScheduleSet(CommonTests):
    @responses.activate(assert_all_requests_are_fired=True)
    def test_post_default(self):
        response = client.post("/tado/schedule/set")
        assert response.status_code == 422

    @responses.activate(assert_all_requests_are_fired=True)
    def test_post(self):
        responses.add(**auth_resp)
        responses.add(**token_resp)
        responses.add(**home_id_resp)
        responses.add(**zones_resp)
        responses.add(**active_timetable_resp)
        responses.add(**active_timetable_resp)
        responses.add(**active_timetable_resp)
        responses.add(
            method=responses.PUT,
            url="http://localhost:8081/api/v2/homes/123/zones/1/schedule/timetables/0/blocks/MONDAY_TO_SUNDAY",
            headers={"Authorization": "Bearer access-token"},
            match=(
                responses.matchers.json_params_matcher(
                    [
                        {
                            "dayType": "MONDAY_TO_SUNDAY",
                            "start": "00:00",
                            "end": "09:58",
                            "geolocationOverride": False,
                            "setting": {
                                "type": "HEATING",
                                "power": "OFF",
                                "temperature": None,
                            },
                        },
                        {
                            "dayType": "MONDAY_TO_SUNDAY",
                            "start": "09:58",
                            "end": "10:43",
                            "geolocationOverride": False,
                            "setting": {
                                "type": "HEATING",
                                "power": "ON",
                                "temperature": {"celsius": 17.5, "fahrenheit": 63.5},
                            },
                        },
                        {
                            "dayType": "MONDAY_TO_SUNDAY",
                            "start": "10:43",
                            "end": "17:00",
                            "geolocationOverride": False,
                            "setting": {
                                "type": "HEATING",
                                "power": "ON",
                                "temperature": {"celsius": 21, "fahrenheit": 69.8},
                            },
                        },
                        {
                            "dayType": "MONDAY_TO_SUNDAY",
                            "start": "17:00",
                            "end": "23:15",
                            "geolocationOverride": False,
                            "setting": {
                                "type": "HEATING",
                                "power": "ON",
                                "temperature": {"celsius": 22.5, "fahrenheit": 72.5},
                            },
                        },
                        {
                            "dayType": "MONDAY_TO_SUNDAY",
                            "start": "23:15",
                            "end": "00:00",
                            "geolocationOverride": False,
                            "setting": {
                                "type": "HEATING",
                                "power": "OFF",
                                "temperature": None,
                            },
                        },
                    ],
                ),
            ),
        )
        responses.add(
            method=responses.PUT,
            url="http://localhost:8081/api/v2/homes/123/zones/2/schedule/timetables/0/blocks/MONDAY_TO_SUNDAY",
            headers={"Authorization": "Bearer access-token"},
        )
        responses.add(
            method=responses.PUT,
            url="http://localhost:8081/api/v2/homes/123/zones/3/schedule/timetables/0/blocks/MONDAY_TO_SUNDAY",
            headers={"Authorization": "Bearer access-token"},
        )
        response = client.post(
            "/tado/schedule/set",
            json={"name": "Schedule 3.1", "variables": {"var2": "11:00"}},
        )
        assert response.status_code == 200
