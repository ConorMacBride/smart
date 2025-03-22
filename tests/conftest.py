import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, PropertyMock

import pytest

from smart.schedule import Schedule
from smart.tado import TadoClient


class EnvResponse:
    def __init__(self, text):
        self.text = text


@pytest.fixture
def tado_client():
    return create_tado_client()


def create_tado_client():
    env = "http://localhost:8080/webapp/env.js"

    def get_env(url):
        assert url == env
        with (Path(__file__).parent / "mock_env.txt").open() as fp:
            text = fp.read().strip()
        return EnvResponse(text=text)

    requests_session = Mock()
    requests_session.get.side_effect = get_env
    client = TadoClient(
        data=".",
        env=env,
        oauth2_endpoint="http://localhost:8080/oauth2",
        requests_session=requests_session,
    )
    client.requests_session = Mock()
    return client


@pytest.fixture
def mock_tado_auth():
    with patch(
        "smart.tado.TadoClient.auth", new_callable=PropertyMock
    ) as mock_property:
        mock_property.return_value = {"Authorization": "Bearer access-token"}
        yield mock_property


@pytest.fixture
def mock_tado_home_id():
    with patch(
        "smart.tado.TadoClient.home_id", new_callable=PropertyMock
    ) as mock_property:
        mock_property.return_value = "123"
        yield mock_property


@pytest.fixture
def mock_active_timetable():
    with patch(
        "smart.schedule.ZoneSchedule.active_timetable", new_callable=PropertyMock
    ) as mock_property:
        mock_property.return_value = 0
        yield mock_property


@pytest.fixture
def schedule():
    with patch("smart.schedule.ZoneSchedule", side_effect=Mock):
        zones = [
            {"id": 1, "name": "Dining Room", "type": "HEATING"},
            {"id": 2, "name": "Bathroom", "type": "HEATING"},
            {"id": 3, "name": "Living Room", "type": "HEATING"},
        ]
        tado_client = Mock()
        tado_client.zones = zones
        tado_client.data = Path(tempfile.mkdtemp())
        yield Schedule(tado_client)
