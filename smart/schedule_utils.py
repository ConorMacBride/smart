import copy
import re
import datetime
from collections import UserDict
from typing import Mapping, List, MutableMapping

_TIME_FMT = r"[0-9]{2}:[0-9]{2}"
TIME_FMT = re.compile(_TIME_FMT)
DYNAMIC_TIME_FMT = re.compile(rf"{{([A-Za-z0-9_]+)(\|([+-])({_TIME_FMT}))?}}")


def create_block(
    start: str, end: str, temperature: float | int
) -> Mapping | List[Mapping]:
    if temperature > 0:
        celsius = round(temperature, 1)
        fahrenheit = round(celsius * 9 / 5 + 32, 1)
        setting = {
            "type": "HEATING",
            "power": "ON",
            "temperature": {
                "celsius": celsius,
                "fahrenheit": fahrenheit,
            },
        }
    else:
        setting = {
            "type": "HEATING",
            "power": "OFF",
            "temperature": None,
        }

    return {
        "dayType": "MONDAY_TO_SUNDAY",
        "start": start,
        "end": end,
        "geolocationOverride": False,
        "setting": setting,
    }


def by_time(block: Mapping) -> datetime.datetime:
    return datetime.datetime.strptime(block["time"], "%H:%M")


def _parse_dynamic_time(time: str, /, **kwargs) -> str:
    m = re.fullmatch(DYNAMIC_TIME_FMT, time)
    if m is None:
        raise ValueError(f"`{time}` not a valid dynamic format.")
    variable, offset = m[1], m[2]
    dt = datetime.datetime.strptime(kwargs[variable], "%H:%M")
    if offset is not None:
        sign, duration = m[3], m[4]
        dt_offset = datetime.datetime.strptime(duration, "%H:%M")
        minutes = 60 * dt_offset.hour + dt_offset.minute
        if sign == "-":
            minutes = -minutes
        dt = dt + datetime.timedelta(minutes=minutes)
    return dt.strftime("%H:%M")


def _parse_time(time: str) -> str:
    m = re.fullmatch(TIME_FMT, time)
    if m is None:
        raise ValueError(f"`{time}` not a valid static format.")
    return m[0]


def parse_dynamic_time(time, **kwargs):
    if time.startswith("{"):
        time = _parse_dynamic_time(time, **kwargs)
    else:
        time = _parse_time(time)
    return time


def parse_dynamic_times(schedule: List[MutableMapping], /, **kwargs) -> None:
    for block in schedule:
        block["time"] = parse_dynamic_time(block["time"], **kwargs)


class ScheduleVariables(UserDict):
    DEFAULT = "default"
    GLOBAL = "global"
    KWARG = "kwarg"

    def __getitem__(self, key):
        if key in self.data:
            return self.data[key]["value"]
        raise KeyError(key)

    def __setitem__(self, key, item):
        if not (isinstance(item, dict) and "value" in item and "type" in item):
            raise NotImplementedError(
                "Use `add_default`, `add_global`, or `add_kwarg`."
            )
        self.data[key] = item

    def __eq__(self, other: MutableMapping):
        a = {k: v["value"] for k, v in self.data.items()}
        if isinstance(other, ScheduleVariables):
            b = {k: v["value"] for k, v in other.data.items()}
            return a == b
        if a == other:
            return True
        return self.data == other

    def copy(self):
        return ScheduleVariables(copy.deepcopy(self.data))

    @property
    def globals(self):
        return {
            k for k, v in self.data.items() if v["type"] == ScheduleVariables.GLOBAL
        }

    def _existing_type(self, key):
        return self.data.get(key, {}).get("type", None)

    def add_default(self, **kwargs):
        for k, v in kwargs.items():
            if self._existing_type(k) not in {
                ScheduleVariables.GLOBAL,
                ScheduleVariables.KWARG,
            }:
                self.data[k] = {"value": v, "type": ScheduleVariables.DEFAULT}

    def add_global(self, **kwargs):
        for k, v in kwargs.items():
            if self._existing_type(k) != ScheduleVariables.KWARG:
                self.data[k] = {"value": v, "type": ScheduleVariables.GLOBAL}

    def add_kwarg(self, **kwargs):
        for k, v in kwargs.items():
            self.data[k] = {"value": v, "type": ScheduleVariables.KWARG}
