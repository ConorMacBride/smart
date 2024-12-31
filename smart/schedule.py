import json
import tomllib
from functools import cached_property
from typing import MutableMapping, List, Mapping, Tuple, Dict, Union

from smart.tado import TadoClient
from smart.schedule_utils import load_schedule, ScheduleVariables


class ZoneSchedule:
    def __init__(self, client: TadoClient, zone: Mapping):
        self.client: TadoClient = client
        self.zone_id: int = zone["id"]
        self.zone_name: str = zone["name"]
        self.json: List[MutableMapping] = []

    @cached_property
    def active_timetable(self) -> int:
        url = self.endpoint + "/activeTimetable"
        r = self.client.requests_session.get(url=url, headers={**self.client.auth})
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
        r = self.client.requests_session.get(url=url, headers={**self.client.auth})
        r.raise_for_status()
        self.json = r.json()

    def push(self) -> None:
        """Set the current schedule."""
        url = (
            self.endpoint
            + f"/timetables/{self.active_timetable}/blocks/MONDAY_TO_SUNDAY"
        )
        r = self.client.requests_session.put(
            url=url, json=self.json, headers={**self.client.auth}
        )
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
        self.current_variables: MutableMapping = {}

    def pull(self) -> None:
        """Get the current schedule."""
        for schedule in self.zone_schedules:
            schedule.pull()

    def push(self) -> None:
        """Set the current schedule."""
        for schedule in self.zone_schedules:
            schedule.push()
        self.active_schedule = self.current_schedule, self.current_variables

    def set(self, name: str = None, /, refresh: bool = False, **kwargs) -> None:
        """Load a schedule."""
        variables = ScheduleVariables()
        if name is None:
            name, variables = self.active_schedule
            if refresh:  # only keep kwarg variables
                variables = {k: v for k, v in variables.items() if v["type"] == "kwarg"}
            variables = ScheduleVariables(variables)
        variables.add_kwarg(**kwargs)
        selected_schedule, schedule_metadata = self.get(
            client=self.client, name=name, variables=variables
        )
        for schedule in self.zone_schedules:
            schedule.set(selected_schedule)
        self.current_schedule = name
        self.current_variables = schedule_metadata

    @classmethod
    def get(
        cls,
        client: TadoClient,
        name: str = None,
        load: bool = True,
        variables: ScheduleVariables = None,
        **kwargs,
    ) -> Union[MutableMapping, Tuple[MutableMapping, Dict[str, MutableMapping]]]:
        """Return schedules."""
        if name is None and kwargs:
            raise ValueError("Cannot pass `kwargs` to `get` when `name` not specified.")

        global_variables = Schedule.variables(client)
        schedules = {}
        path = client.data / "schedules"

        for config in path.glob("*.toml"):
            with open(config, "rb") as fp:
                schedule = tomllib.load(fp)
            metadata = schedule.pop("metadata", {})
            variants = [metadata] + schedule.pop("variant", [])

            for variant in variants:
                variant_metadata = {**metadata, **variant}
                variant_name = variant_metadata.pop("name")
                variant_variables = (
                    variables.copy() if variables else ScheduleVariables()
                )

                variant_variables.add_default(
                    **{
                        k: v
                        for k, v in variant_metadata.items()
                        if k not in variant_variables
                    }
                )
                variant_variables.add_global(
                    **{
                        k: v
                        for k, v in global_variables.items()
                        if k in variant_metadata and k not in variant_variables.globals
                    }
                )
                variant_variables.add_kwarg(
                    **{k: v for k, v in kwargs.items() if k in variant_metadata}
                )

                variables_values = {
                    k: v["value"] for k, v in variant_variables.data.items()
                }

                if name:
                    if name == variant_name:
                        if load:
                            return load_schedule(
                                schedule, **variables_values
                            ), variant_variables.data
                        return variant_variables.data
                    continue

                schedules[variant_name] = (
                    (
                        load_schedule(schedule, **variables_values),
                        variant_variables.data,
                    )
                    if load
                    else variant_variables.data
                )

        if not schedules:
            raise ValueError("No schedules found.")
        return schedules

    @property
    def active_schedule(self) -> Tuple[str, MutableMapping]:
        path = self.client.data / "active_schedule.json"
        with open(path) as fp:
            data = json.load(fp)
        return data["schedule"], data["variables"]

    @active_schedule.setter
    def active_schedule(self, value: Tuple[str, MutableMapping]) -> None:
        schedule, variables = value
        data = {"schedule": schedule, "variables": variables}
        path = self.client.data / "active_schedule.json"
        with path.open("w") as fp:
            json.dump(data, fp)

    @classmethod
    def variables(
        cls, client: TadoClient, update: Mapping[str, str] = None
    ) -> Dict[str, str]:
        """Return global schedule variables."""
        path = client.data / "variables.json"
        if path.exists():
            with path.open() as fp:
                v = json.load(fp)
        else:
            v = {}
        if update:
            v.update(update)
            with path.open("w") as fp:
                json.dump(v, fp)
        return v

    def is_active(self):
        """Check if the schedule is active."""
        active_schedule, active_variables = self.active_schedule
        return (active_schedule == self.current_schedule) and (
            ScheduleVariables(active_variables)
            == ScheduleVariables(self.current_variables)
        )
