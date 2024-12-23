import functools
import shutil
from pathlib import Path
from unittest.mock import Mock

import pytest

from smart.schedule import Schedule, ZoneSchedule
from smart.schedule_utils import parse_dynamic_times


class HttpResponse:
    def __init__(self, json=None):
        self._json = json

    def json(self):
        return self._json

    def raise_for_status(self):
        return


def setup_data(func):
    @functools.wraps(func)
    def wrapper(self, tmp_path, schedule):
        schedule.client.data = tmp_path
        dest = tmp_path / "schedules"
        dest.mkdir()
        shutil.copy(
            Path(__file__).parent.parent / "sample_schedule_1.toml", dest / "s1.toml"
        )
        shutil.copy(
            Path(__file__).parent.parent / "sample_schedule_2.toml", dest / "s2.toml"
        )
        shutil.copy(
            Path(__file__).parent.parent / "sample_schedule_3.toml", dest / "s3.toml"
        )
        func(self, tmp_path, schedule)

    return wrapper


def test_parse_dynamic_times_raises_exception():
    with pytest.raises(KeyError):
        parse_dynamic_times([{"time": "{var2}"}])
    for time in ["{var1|01:00}", "{var1|+1:00}", "{var1|-1:00}"]:
        with pytest.raises(ValueError, match="not a valid dynamic format"):
            parse_dynamic_times([{"time": time}], var1="07:00")
    for time in ["aaa", "7:00", "0700"]:
        with pytest.raises(ValueError, match="not a valid static format"):
            parse_dynamic_times([{"time": time}])


class TestSchedule:
    def test_zone_schedules(self):
        zones = [
            {"id": 1, "name": "Dining Room", "type": "HEATING"},
            {"id": 2, "name": "Bathroom", "type": "HEATING"},
            {"id": 3, "name": "Living Room", "type": "HEATING"},
        ]
        tado_client = Mock()
        tado_client.zones = zones

        schedule = Schedule(tado_client)

        assert len(schedule.zone_schedules) == 3
        for idx, zone in enumerate(schedule.zone_schedules):
            assert isinstance(zone, ZoneSchedule)
            assert zone.client is tado_client
            assert zone.zone_id == zones[idx]["id"]
            assert zone.zone_name == zones[idx]["name"]

    def test_pull(self, schedule):
        schedule.pull()

        assert len(schedule.zone_schedules) == 3
        for zone in schedule.zone_schedules:
            zone.pull.assert_called_once()

    def test_push(self, tmp_path, schedule):
        schedule.current_schedule = "current-schedule"
        schedule.current_kwargs = {"varA": "val1", "varB": 2}
        schedule.client.data = tmp_path

        schedule.push()

        assert len(schedule.zone_schedules) == 3
        for zone in schedule.zone_schedules:
            zone.push.assert_called_once()
        assert schedule.active_schedule == (
            "current-schedule",
            {"varA": "val1", "varB": 2},
        )

    @setup_data
    def test_set(self, tmp_path, schedule):
        all_schedules = Schedule.get(client=schedule.client, name="Schedule 1")
        assert len(all_schedules["dining_room"]) == 5
        assert len(all_schedules["bathroom"]) == 5
        assert len(all_schedules["living_room"]) == 5

        schedule.set("Schedule 1")

        assert len(schedule.zone_schedules) == 3
        for zone in schedule.zone_schedules:
            zone.set.assert_called_once_with(all_schedules)
        assert schedule.current_schedule == "Schedule 1"
        assert schedule.current_kwargs == {}

    @setup_data
    def test_set_kwargs(self, tmp_path, schedule):
        all_schedules = Schedule.get(
            client=schedule.client, name="Schedule 2", var1="07:00"
        )

        schedule.set("Schedule 2", var1="07:00")

        assert len(schedule.zone_schedules) == 3
        for zone in schedule.zone_schedules:
            zone.set.assert_called_once_with(all_schedules)
        assert schedule.current_schedule == "Schedule 2"
        assert schedule.current_kwargs == {"var1": "07:00"}

    @setup_data
    def test_get(self, tmp_path, schedule):
        schedule_1 = Schedule.get(client=schedule.client, name="Schedule 1")
        assert len(schedule_1["dining_room"]) == 5
        assert len(schedule_1["bathroom"]) == 5
        assert len(schedule_1["living_room"]) == 5
        assert schedule_1["dining_room"][1]["start"] == "06:30"
        assert schedule_1["dining_room"][2]["start"] == "10:20"

        schedule_31 = Schedule.get(client=schedule.client, name="Schedule 3.1")
        assert len(schedule_31["dining_room"]) == 5
        assert len(schedule_31["bathroom"]) == 5
        assert len(schedule_31["living_room"]) == 5
        assert schedule_31["dining_room"][1]["start"] == "08:58"
        assert schedule_31["dining_room"][2]["start"] == "10:43"

    @setup_data
    def test_get_no_name(self, tmp_path, schedule):
        all_schedules = Schedule.get(client=schedule.client)
        assert len(all_schedules) == 5
        assert len(all_schedules["Schedule 1"]["dining_room"]) == 5
        assert len(all_schedules["Schedule 1"]["bathroom"]) == 5
        assert len(all_schedules["Schedule 1"]["living_room"]) == 5
        assert len(all_schedules["Schedule 2"]["dining_room"]) == 5
        assert len(all_schedules["Schedule 2"]["bathroom"]) == 5
        assert len(all_schedules["Schedule 2"]["living_room"]) == 5

    @setup_data
    def test_get_no_load(self, tmp_path, schedule):
        schedule_2 = Schedule.get(
            client=schedule.client, name="Schedule 2", load=False, var2="10:10"
        )
        assert schedule_2["var1"] == "09:00"
        assert schedule_2["var2"] == "10:10"

    @setup_data
    def test_get_no_name_no_load(self, tmp_path, schedule):
        all_schedules = Schedule.get(client=schedule.client, load=False)
        assert len(all_schedules) == 5
        assert len(all_schedules["Schedule 1"]) == 0
        assert all_schedules["Schedule 2"]["var1"] == "09:00"
        assert all_schedules["Schedule 2"]["var2"] == "10:00"
        assert all_schedules["Schedule 3"]["var1"] == "09:00"
        assert all_schedules["Schedule 3"]["var2"] == "10:00"
        assert all_schedules["Schedule 3.1"]["var1"] == "09:30"
        assert all_schedules["Schedule 3.1"]["var2"] == "10:00"
        assert all_schedules["Schedule 3.2"]["var1"] == "09:00"
        assert all_schedules["Schedule 3.2"]["var2"] == "09:30"

    @setup_data
    def test_get_raises_exception(self, tmp_path, schedule):
        with pytest.raises(ValueError, match="No schedules found."):
            Schedule.get(client=schedule.client, name="Schedule A")
        with pytest.raises(
            ValueError, match="Cannot pass `kwargs` to `get` when `name` not specified."
        ):
            Schedule.get(client=schedule.client, var1="07:00")


class TestZoneSchedule:
    def test_active_timetable(self, tado_client, mock_tado_auth, mock_tado_home_id):
        zone_schedule = ZoneSchedule(
            client=tado_client, zone={"id": 1, "name": "Dining Room"}
        )
        tado_client.requests_session.get.return_value = HttpResponse(
            json={"id": 0, "type": "ONE_DAY"}
        )

        active_timetable = zone_schedule.active_timetable

        tado_client.requests_session.get.assert_called_once_with(
            url="http://localhost:8080/api/v2/homes/123/zones/1/schedule/activeTimetable",
            headers={"Authorization": "Bearer access-token"},
        )
        assert active_timetable == 0

    def test_active_timetable_raises_exception(
        self, tado_client, mock_tado_auth, mock_tado_home_id
    ):
        zone_schedule = ZoneSchedule(
            client=tado_client, zone={"id": 1, "name": "Dining Room"}
        )
        tado_client.requests_session.get.return_value = HttpResponse(
            json={"id": 0, "type": "WEEKLY"}
        )

        with pytest.raises(
            NotImplementedError, match="Only single day schedule is supported."
        ):
            zone_schedule.active_timetable  # noqa

    def test_pull(
        self, tado_client, mock_tado_auth, mock_tado_home_id, mock_active_timetable
    ):
        zone_schedule = ZoneSchedule(
            client=tado_client, zone={"id": 1, "name": "Dining Room"}
        )
        schedule = [
            {"time": "06:30", "temperature": 20.0},
            {"time": "10:20", "temperature": 21.0},
            {"time": "14:00", "temperature": 22.0},
            {"time": "17:00", "temperature": 21.0},
            {"time": "21:00", "temperature": 20.0},
        ]
        tado_client.requests_session.get.return_value = HttpResponse(json=schedule)

        zone_schedule.pull()

        tado_client.requests_session.get.assert_called_once_with(
            url="http://localhost:8080/api/v2/homes/123/zones/1/schedule/timetables/0/blocks",
            headers={"Authorization": "Bearer access-token"},
        )
        assert zone_schedule.json == schedule

    def test_push(
        self, tado_client, mock_tado_auth, mock_tado_home_id, mock_active_timetable
    ):
        zone_schedule = ZoneSchedule(
            client=tado_client, zone={"id": 1, "name": "Dining Room"}
        )
        zone_schedule.json = [
            {"time": "06:30", "temperature": 20.0},
            {"time": "10:20", "temperature": 21.0},
            {"time": "14:00", "temperature": 22.0},
            {"time": "17:00", "temperature": 21.0},
            {"time": "21:00", "temperature": 20.0},
        ]

        zone_schedule.push()

        tado_client.requests_session.put.assert_called_once_with(
            url="http://localhost:8080/api/v2/homes/123/zones/1/schedule/timetables/0/blocks/MONDAY_TO_SUNDAY",
            json=zone_schedule.json,
            headers={"Authorization": "Bearer access-token"},
        )

    def test_set(self, tado_client):
        zone_schedule = ZoneSchedule(
            client=tado_client, zone={"id": 1, "name": "Dining Room"}
        )
        schedule = {
            "dining_room": [
                {"time": "06:30", "temperature": 20.0},
                {"time": "10:20", "temperature": 21.0},
                {"time": "14:00", "temperature": 22.0},
                {"time": "17:00", "temperature": 21.0},
                {"time": "21:00", "temperature": 20.0},
            ]
        }

        zone_schedule.set(schedule)

        assert zone_schedule.json == schedule["dining_room"]
