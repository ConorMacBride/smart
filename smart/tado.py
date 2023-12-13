from functools import cached_property

import requests


class Presence:
    __slots__ = ()
    HOME = "HOME"
    AWAY = "AWAY"


class TadoClient:
    def __init__(self, username, password, env=None):
        if env is None:
            env = "https://my.tado.com/webapp/env.js"
        self.username = username
        self.password = password
        self.env = env
        self.oauth_endpoint = self.get_env("apiEndpoint")
        self.client_id = self.get_env("clientId")
        self.client_secret = self.get_env("clientSecret")
        self.v1_endpoint = self.get_env("tgaRestApiEndpoint")
        self.v2_endpoint = self.get_env("tgaRestApiV2Endpoint")

    @cached_property
    def _env(self):
        env = requests.get(url=self.env)
        return env.text

    def get_env(self, key, value=None):
        values = list(
            filter(
                lambda x: key in x.strip(),
                self._env.split("\n"),
            )
        )
        if len(values) == 0:
            if value is not None:
                return value
            raise ValueError(f"`{key}` not in environment.")
        elif len(values) == 1:
            return values[0].split("'")[-2]
        elif len(values) > 1:
            raise ValueError(f"Multiple `{key}` values found in environment.")

    @cached_property
    def access_token(self):
        r = requests.post(
            url=self.oauth_endpoint + "/token",
            data={
                "client_id": self.client_id,
                "grant_type": "password",
                "scope": "home.user",
                "username": self.username,
                "password": self.password,
                "client_secret": self.client_secret,
            },
        )
        r.raise_for_status()
        return r.json()["access_token"]

    @cached_property
    def home_id(self):
        r = requests.get(self.v1_endpoint + "/me", headers={"Authorization": f"Bearer {self.access_token}"})
        r.raise_for_status()
        return r.json()["homeId"]

    @cached_property
    def zones(self):
        zones = f"{self.v2_endpoint}/homes/{self.home_id}/zones"
        r = requests.get(zones, headers={"Authorization": f"Bearer {self.access_token}"})
        r.raise_for_status()
        return r.json()

    def _set_presence(self, presence):
        url = f"{self.v2_endpoint}/homes/{self.home_id}/presenceLock"
        data = {
            "homePresence": presence,
        }
        r = requests.put(url=url, json=data, headers={"Authorization": f"Bearer {self.access_token}"})
        r.raise_for_status()

    def set_home(self):
        self._set_presence(Presence.HOME)

    def set_away(self):
        self._set_presence(Presence.AWAY)

    def get_presence(self):
        url = f"{self.v2_endpoint}/homes/{self.home_id}/state"
        r = requests.get(url=url, headers={"Authorization": f"Bearer {self.access_token}"})
        r.raise_for_status()
        return r.json().get("presence", None)
