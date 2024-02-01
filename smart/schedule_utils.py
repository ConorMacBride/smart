import copy
import re
import datetime
from typing import Mapping, List, MutableMapping

_TIME_FMT = r"[0-9]{2}:[0-9]{2}"
TIME_FMT = re.compile(_TIME_FMT)
DYNAMIC_TIME_FMT = re.compile(rf"{{([A-Za-z0-9_]+)(\|([+-])({_TIME_FMT}))?}}")


def create_block(start: str, end: str, temperature: float | int) -> Mapping | List[Mapping]:
    # Split blocks at midnight
    if not (start == "00:00" or end == "00:00"):
        start_dt = datetime.datetime.strptime(start, "%H:%M")
        end_dt = datetime.datetime.strptime(end, "%H:%M")
        if end_dt < start_dt:  # block includes midnight
            return [
                create_block(start, "00:00", temperature),
                create_block("00:00", end, temperature),
            ]

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


def parse_dynamic_times(schedule: MutableMapping, /, **kwargs) -> None:
    for block in schedule:
        time = block["time"]
        if time.startswith("{"):
            time = _parse_dynamic_time(time, **kwargs)
        else:
            time = _parse_time(time)
        block["time"] = time


def load_schedule(config: Mapping, /, **metadata) -> MutableMapping:
    schedules = {}
    for zone, schedule in config.items():
        schedule = copy.deepcopy(schedule)
        parse_dynamic_times(schedule, **metadata)
        schedule.sort(key=by_time)
        schedules[zone] = []
        n_blocks = len(schedule)
        for idx in range(n_blocks):
            start = schedule[idx]["time"]
            if idx + 1 >= n_blocks:
                end = schedule[0]["time"]
            else:
                end = schedule[idx+1]["time"]
            temperature = schedule[idx]["temperature"]
            block = create_block(start, end, temperature)
            if isinstance(block, list):  # split at midnight
                before_midnight, after_midnight = block
                schedules[zone].insert(0, after_midnight)
                schedules[zone].append(before_midnight)
            else:
                schedules[zone].append(block)
    return schedules
