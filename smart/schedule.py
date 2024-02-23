import json
import tomllib
from functools import cached_property
from typing import MutableMapping, List, Mapping, Tuple

import requests

from smart.tado import TadoClient
from smart.schedule_utils import load_schedule


class ZoneSchedule:
    def __init__(self, client: TadoClient, zone: Mapping):
        self.client: TadoClient = client
        self.zone_id: int = zone["id"]
        self.zone_name: str = zone["name"]
        self.json: List[MutableMapping] = []

    @cached_property
    def active_timetable(self) -> int:
        url = self.endpoint + "/activeTimetable"
        r = requests.get(url=url, headers={**self.client.auth})
        r.raise_for_status()
        data = r.json()
        if data["type"] != "ONE_DAY":
            raise NotImplementedError("Only single day schedule is supported.")
        return data["id"]

    @property
    def endpoint(self) -> str:
        """Zone schedule endpoint."""
        home = f"{self.client.v2_endpoint}/homes/{self.client.home_id}"
        zone = f"{home}/zones/{self.zone_id}"
        schedule = f"{zone}/schedule"
        return schedule

    def pull(self) -> None:
        """Get the current schedule."""
        url = self.endpoint + f"/timetables/{self.active_timetable}/blocks"
        r = requests.get(url=url, headers={**self.client.auth})
        r.raise_for_status()
        self.json = r.json()

    def push(self) -> None:
        """Set the current schedule."""
        url = (
            self.endpoint
            + f"/timetables/{self.active_timetable}/blocks/MONDAY_TO_SUNDAY"
        )
        r = requests.put(url=url, json=self.json, headers={**self.client.auth})
        r.raise_for_status()

    def set(self, schedule: Mapping) -> None:
        """Load a schedule."""
        zone_name = self.zone_name.lower().replace(" ", "_")
        self.json = schedule[zone_name]


class Schedule:
    def __init__(self, client: TadoClient):
        self.client: TadoClient = client
        self.zone_schedules: List[ZoneSchedule] = [
            ZoneSchedule(client=client, zone=zone) for zone in client.zones
        ]
        self.current_schedule: MutableMapping = {}
        self.current_kwargs: MutableMapping = {}

    def pull(self) -> None:
        """Get the current schedule."""
        for schedule in self.zone_schedules:
            schedule.pull()

    def push(self) -> None:
        """Set the current schedule."""
        for schedule in self.zone_schedules:
            schedule.push()
        self.active_schedule = self.current_schedule, self.current_kwargs

    def set(self, name: str, /, **kwargs) -> None:
        """Load a schedule."""
        all_schedules = self.get(client=self.client, name=name, **kwargs)
        for schedule in self.zone_schedules:
            schedule.set(all_schedules)
        self.current_schedule = name
        self.current_kwargs = kwargs

    @classmethod
    def get(
        cls, client: TadoClient, name: str = None, load: bool = True, **kwargs
    ) -> MutableMapping:
        """Return schedules."""
        if name is None and kwargs:
            raise ValueError("Cannot pass `kwargs` to `get` when `name` not specified.")
        schedules = {}
        path = client.data / "schedules"
        for config in path.glob("*.toml"):
            with open(config, "rb") as fp:
                schedule = tomllib.load(fp)
            metadata = schedule.pop("metadata", {})
            variants = schedule.pop("variant", [])
            variants.insert(0, metadata)
            for variant in variants:
                variant_metadata = metadata | variant | kwargs
                variant_name = variant_metadata.pop("name")
                if name:
                    if name == variant_name:
                        if load:
                            return load_schedule(schedule, **variant_metadata)
                        return variant_metadata
                    continue
                if load:
                    schedule_details = load_schedule(schedule, **variant_metadata)
                else:
                    schedule_details = variant_metadata
                schedules[variant_name] = schedule_details
        return schedules

    @property
    def active_schedule(self) -> Tuple[str, MutableMapping]:
        path = self.client.data / "active_schedule.json"
        with open(path) as fp:
            data = json.load(fp)
        return data["schedule"], data["kwargs"]

    @active_schedule.setter
    def active_schedule(self, value: Tuple[str, MutableMapping]) -> None:
        schedule, kwargs = value
        data = {"schedule": schedule, "kwargs": kwargs}
        path = self.client.data / "active_schedule.json"
        with open(path, "w") as fp:
            json.dump(data, fp)
