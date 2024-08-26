from pathlib import Path
from unittest.mock import Mock, patch, PropertyMock

import pytest

from smart.tado import TadoClient


class EnvResponse:
    def __init__(self, text):
        self.text = text

    @property
    def test(self):
        return self.text


@pytest.fixture
def tado_client():
    env = "http://localhost:8080/webapp/env.js"

    def get_env(url):
        if url == env:
            with (Path(__file__).parent / "mock_env.txt").open() as fp:
                text = fp.read().strip()
            return EnvResponse(text=text)
        raise ValueError("url != env")

    requests_session = Mock()
    requests_session.get.side_effect = get_env
    client = TadoClient(
        username="username",
        password="password",
        data=".",
        env=env,
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
