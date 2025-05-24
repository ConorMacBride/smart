import logging
import os
import time
from functools import cached_property
from pathlib import Path

import requests
from pydantic import BaseModel, field_validator


class Presence:
    __slots__ = ()
    HOME = "HOME"
    AWAY = "AWAY"


class Token(BaseModel):
    access_token: str
    expires_in: int
    refresh_token: str

    @field_validator("expires_in", mode="before")
    @classmethod
    def set_expires_in(cls, raw):
        if raw < 30_000_000:  # convert to Unix timestamp
            return int(time.time()) + int(raw)
        return raw


class TadoClient:
    def __init__(
        self,
        data,
        api_endpoint=None,
        requests_session=None,
        oauth2_endpoint=None,
        logger=None,
    ):
        if api_endpoint is None:
            api_endpoint = "https://my.tado.com/api/v2"
        if oauth2_endpoint is None:
            oauth2_endpoint = "https://login.tado.com/oauth2"
        if logger is None:
            logger = logging.getLogger(__name__)
        self.requests_session = requests_session or requests.Session()
        self.logger = logger
        self.data = Path(data)
        self.oauth2_endpoint = oauth2_endpoint
        self.client_id = "1bb50063-6b0c-4d11-bd99-387f4a91cc46"
        self.v2_endpoint = api_endpoint
        self._token = None

    def _refresh_token(self, token: Token) -> Token:
        r = self.requests_session.post(
            self.oauth2_endpoint + "/token",
            data={
                "client_id": self.client_id,
                "grant_type": "refresh_token",
                "refresh_token": token.refresh_token,
            },
        )
        r.raise_for_status()
        self.logger.log(logging.DEBUG, r.json())
        self.logger.log(logging.INFO, "Token refreshed.")
        return Token(**r.json())

    def _authenticate(self) -> Token:
        verify = self.requests_session.post(
            self.oauth2_endpoint + "/device_authorize",
            data={
                "client_id": self.client_id,
                "scope": "offline_access",
            },
        )
        verify.raise_for_status()
        self.logger.log(logging.DEBUG, verify.json())
        self.logger.log(
            logging.INFO,
            f"Log in to tadoº: {verify.json()['verification_uri_complete']}",
        )
        start_time = time.time()
        while time.time() - start_time < verify.json()["expires_in"]:
            self.logger.log(logging.INFO, "Checking for token...")
            r = self.requests_session.post(
                self.oauth2_endpoint + "/token",
                data={
                    "client_id": self.client_id,
                    "device_code": verify.json()["device_code"],
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
            )
            if r.status_code == 200:
                self.logger.log(logging.DEBUG, r.json())
                self.logger.log(logging.INFO, "Token received.")
                return Token(**r.json())
            time.sleep(verify.json()["interval"])
        raise TimeoutError("Timed out waiting for token")

    @property
    def token(self):
        token_path = self.data / "token.json"
        if self._token is None:
            try:
                with token_path.open() as fp:
                    self._token = Token.model_validate_json(fp.read())
            except FileNotFoundError:
                self._token = self._authenticate()
                with token_path.open("w") as fp:
                    os.chmod(token_path, 0o600)
                    fp.write(self._token.model_dump_json())
        if self._token.expires_in - time.time() < 60:
            self._token = self._refresh_token(self._token)
            with token_path.open("w") as fp:
                os.chmod(token_path, 0o600)
                fp.write(self._token.model_dump_json())
        return self._token

    @property
    def auth(self):
        return {"Authorization": f"Bearer {self.token.access_token}"}

    @cached_property
    def home_id(self):
        r = self.requests_session.get(self.v2_endpoint + "/me", headers={**self.auth})
        r.raise_for_status()
        return r.json()["homes"][0]["id"]

    @cached_property
    def zones(self):
        zones = f"{self.v2_endpoint}/homes/{self.home_id}/zones"
        r = self.requests_session.get(zones, headers={**self.auth})
        r.raise_for_status()
        return r.json()

    def _set_presence(self, presence):
        url = f"{self.v2_endpoint}/homes/{self.home_id}/presenceLock"
        data = {
            "homePresence": presence,
        }
        r = self.requests_session.put(url, json=data, headers={**self.auth})
        r.raise_for_status()

    def set_home(self):
        self._set_presence(Presence.HOME)

    def set_away(self):
        self._set_presence(Presence.AWAY)

    def get_presence(self):
        url = f"{self.v2_endpoint}/homes/{self.home_id}/state"
        r = self.requests_session.get(url, headers={**self.auth})
        r.raise_for_status()
        return r.json().get("presence", None)
