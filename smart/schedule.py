import copy
import json
import tomllib
import datetime
from functools import cached_property
from typing import MutableMapping, List, Mapping, Tuple, Dict, Union

from smart.tado import TadoClient
from smart.schedule_utils import (
    ScheduleVariables,
    parse_dynamic_times,
    by_time,
    create_block,
)


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

        schedules = Schedules(
            client.data / "schedules",
            Schedule.variables(client),
            variables,
            **kwargs,
        )

        if name:
            if name not in schedules.schedules:
                raise ValueError("No schedules found.")
            if load:
                return schedules.load(name), schedules.variables(name)
            return schedules.variables(name)

        schedules = {
            name: (
                (
                    schedules.load(name),
                    schedules.variables(name),
                )
                if load
                else schedules.variables(name)
            )
            for name in schedules.schedules.keys()
        }
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


class Schedules:
    def __init__(
        self,
        path,
        global_variables: Dict = None,
        variables: ScheduleVariables = None,
        **kwargs,
    ):
        self.schedules = {}
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
                if global_variables:
                    variant_variables.add_global(
                        **{
                            k: v
                            for k, v in global_variables.items()
                            if k in variant_metadata
                            and k not in variant_variables.globals
                        }
                    )
                variant_variables.add_kwarg(
                    **{k: v for k, v in kwargs.items() if k in variant_metadata}
                )

                self.schedules[variant_name] = {
                    "schedule": schedule,
                    "variables": variant_variables,
                }

    def variables(self, name: str):
        return self.schedules[name]["variables"].data

    def variables_values(self, name: str):
        return {
            k: v["value"] for k, v in self.schedules[name]["variables"].data.items()
        }

    def load(self, name: str):
        schedule = {}
        for zone_name in self.schedules[name]["schedule"].keys():
            schedule[zone_name] = self.load_zone(name, zone_name)
        return schedule

    def load_zone(self, name: str, zone: str, tado_format: bool = True):
        schedule = self.schedules[name]["schedule"][zone]

        base_timetable = []
        for block in schedule:
            if "copy" in block:
                copy_schedule = block["copy"]
                if ":" in copy_schedule:
                    copy_schedule_name, copy_schedule_zone = copy_schedule.split(":")
                else:
                    copy_schedule_name, copy_schedule_zone = copy_schedule, zone
                copy_schedule_name = copy_schedule_name or name
                copy_schedule_zone = copy_schedule_zone or zone
                base_timetable = self.load_zone(
                    copy_schedule_name, copy_schedule_zone, tado_format=False
                )
                break
        schedule = list(filter(lambda block: "copy" not in block, schedule))

        timetable = self.schedule_to_timetable(schedule, **self.variables_values(name))
        if base_timetable:
            timetable = self.merge_timetables(base_timetable, timetable)

        if tado_format:
            return [create_block(*block) for block in timetable]
        return timetable

    @staticmethod
    def merge_timetables(base_timetable, timetable):
        timetable = [(*block, 0) for block in base_timetable] + [
            (*block, 1) for block in timetable
        ]
        timetable = sorted(timetable, key=lambda x: x[0])

        # Merge timetables
        last_base_block = next(
            filter(lambda block: block[-1] == 0, reversed(timetable))
        )  # last base block
        merged_timetable = []
        start_block = None
        for block in timetable:
            if block[-1] == 1:
                if block[2] == "reset":
                    merged_timetable.append(
                        (block[0], last_base_block[1], last_base_block[2])
                    )
                    start_block = None
                else:
                    start_block = block
                    merged_timetable.append(block[:-1])
            else:
                last_base_block = block[:-1]
                if start_block is None:
                    merged_timetable.append(block[:-1])

        # Cut overlapping end times
        timetable = []
        for idx in range(len(merged_timetable) - 1):
            timetable.append(
                (
                    merged_timetable[idx][0],
                    merged_timetable[idx + 1][0],
                    merged_timetable[idx][2],
                )
            )
        timetable.append(
            (
                merged_timetable[-1][0],
                merged_timetable[0][0],
                merged_timetable[-1][2],
            )
        )
        merged_timetable = timetable

        # Remove empty time ranges
        merged_timetable = [block for block in merged_timetable if block[0] != block[1]]

        # Remove redundant splits
        merged = []
        current_start, current_end, current_temperature = merged_timetable[0]
        for start, end, temperature in merged_timetable[1:]:
            if temperature == current_temperature:
                current_end = end
            else:
                merged.append((current_start, current_end, current_temperature))
                current_start, current_end, current_temperature = (
                    start,
                    end,
                    temperature,
                )
        merged.append((current_start, current_end, current_temperature))
        merged_timetable = merged

        return merged_timetable

    @staticmethod
    def schedule_to_timetable(
        schedule: List[MutableMapping], /, **metadata
    ) -> List[Tuple[str, str, Union[float | int]]]:
        data = []
        schedule = copy.deepcopy(schedule)
        parse_dynamic_times(schedule, **metadata)
        schedule.sort(key=by_time)
        n_blocks = len(schedule)
        for idx in range(n_blocks):
            start = schedule[idx]["time"]
            if idx + 1 >= n_blocks:
                end = schedule[0]["time"]
            else:
                end = schedule[idx + 1]["time"]
            temperature = schedule[idx]["temperature"]

            # Split blocks at midnight
            if not (start == "00:00" or end == "00:00"):
                start_dt = datetime.datetime.strptime(start, "%H:%M")
                end_dt = datetime.datetime.strptime(end, "%H:%M")
                if end_dt < start_dt:  # block includes midnight
                    data.insert(0, ("00:00", end, temperature))
                    data.append((start, "00:00", temperature))
                    continue

            data.append((start, end, temperature))

        return sorted(data, key=lambda block: block[0])
