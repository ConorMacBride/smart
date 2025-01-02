import functools
import json
import shutil
from pathlib import Path
from unittest.mock import Mock

import pytest

from smart.schedule import Schedule, ZoneSchedule, Schedules


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
        shutil.copy(
            Path(__file__).parent.parent / "sample_schedule_4.toml", dest / "s4.toml"
        )
        func(self, tmp_path, schedule)

    return wrapper


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
        schedule.current_variables = {
            "varA": {"value": "val1", "type": "kwarg"},
            "varB": {"value": 2, "type": "global"},
        }
        schedule.client.data = tmp_path

        schedule.push()

        assert len(schedule.zone_schedules) == 3
        for zone in schedule.zone_schedules:
            zone.push.assert_called_once()
        assert schedule.active_schedule == (
            "current-schedule",
            {
                "varA": {"value": "val1", "type": "kwarg"},
                "varB": {"value": 2, "type": "global"},
            },
        )

    @setup_data
    def test_set(self, tmp_path, schedule):
        all_schedules = Schedule.get(client=schedule.client, name="Schedule 1")
        assert len(all_schedules[0]["dining_room"]) == 5
        assert len(all_schedules[0]["bathroom"]) == 5
        assert len(all_schedules[0]["living_room"]) == 5
        assert all_schedules[1] == {}

        schedule.set("Schedule 1")

        assert len(schedule.zone_schedules) == 3
        for zone in schedule.zone_schedules:
            zone.set.assert_called_once_with(all_schedules[0])
        assert schedule.current_schedule == "Schedule 1"
        assert schedule.current_variables == {}

    @setup_data
    def test_set_variables(self, tmp_path, schedule):
        all_schedules = Schedule.get(
            client=schedule.client, name="Schedule 2", var1="07:00"
        )
        assert all_schedules[1] == {
            "var1": {"value": "07:00", "type": "kwarg"},
            "var2": {"value": "10:00", "type": "default"},
        }

        schedule.set("Schedule 2", var1="07:00")

        assert len(schedule.zone_schedules) == 3
        for zone in schedule.zone_schedules:
            zone.set.assert_called_once_with(all_schedules[0])
        assert schedule.current_schedule == "Schedule 2"
        assert schedule.current_variables == {
            "var1": {"value": "07:00", "type": "kwarg"},
            "var2": {"value": "10:00", "type": "default"},
        }

    @setup_data
    def test_set_current_schedule(self, tmp_path, schedule):
        all_schedules = Schedule.get(
            client=schedule.client, name="Schedule 3.1", var1="08:00"
        )
        active_schedule = schedule.client.data / "active_schedule.json"
        active_schedule.write_text(
            json.dumps(
                {
                    "schedule": "Schedule 3.1",
                    "variables": {
                        "var1": {"value": "09:00", "type": "kwarg"},
                        "var2": {"value": "10:00", "type": "default"},
                        "var3": {"value": "global", "type": "default"},
                    },
                }
            )
        )
        assert all_schedules[1] == {
            "var1": {"value": "08:00", "type": "kwarg"},
            "var2": {"value": "10:00", "type": "default"},
            "var3": {"value": "global", "type": "default"},
        }

        schedule.set(var1="08:00")

        assert len(schedule.zone_schedules) == 3
        for zone in schedule.zone_schedules:
            zone.set.assert_called_once_with(all_schedules[0])
        assert schedule.current_schedule == "Schedule 3.1"
        assert schedule.current_variables == {
            "var1": {"value": "08:00", "type": "kwarg"},
            "var2": {"value": "10:00", "type": "default"},
            "var3": {"value": "global", "type": "default"},
        }

    @setup_data
    def test_get(self, tmp_path, schedule):
        (schedule.client.data / "variables.json").write_text(
            '{"var3": "14:00", "var4": "15:00"}'
        )

        schedule_1 = Schedule.get(client=schedule.client, name="Schedule 1")
        assert len(schedule_1[0]["dining_room"]) == 5
        assert len(schedule_1[0]["bathroom"]) == 5
        assert len(schedule_1[0]["living_room"]) == 5
        assert schedule_1[0]["dining_room"][1]["start"] == "06:30"
        assert schedule_1[0]["dining_room"][2]["start"] == "10:20"
        assert schedule_1[1] == {}

        schedule_31 = Schedule.get(client=schedule.client, name="Schedule 3.1")
        assert len(schedule_31[0]["dining_room"]) == 5
        assert len(schedule_31[0]["bathroom"]) == 5
        assert len(schedule_31[0]["living_room"]) == 5
        assert schedule_31[0]["dining_room"][1]["start"] == "08:58"
        assert schedule_31[0]["dining_room"][2]["start"] == "10:43"
        assert schedule_31[1] == {
            "var1": {"value": "09:30", "type": "default"},
            "var2": {"value": "10:00", "type": "default"},
            "var3": {"value": "14:00", "type": "global"},
        }

        s4, v4 = Schedule.get(client=schedule.client, name="Schedule 4")

        def f(v):
            return [
                (
                    x["start"],
                    x["end"],
                    (x["setting"]["temperature"] or {}).get("celsius", None),
                )
                for x in v
            ]

        assert len(s4) == 3
        assert f(s4["bathroom"]) == [
            ("00:00", "06:30", None),
            ("06:30", "23:30", 18),
            ("23:30", "00:00", None),
        ]
        assert f(s4["dining_room"]) == [
            ("00:00", "06:15", None),
            ("06:15", "06:30", 17.5),
            ("06:30", "07:30", 25),
            ("07:30", "09:00", 17.5),
            ("09:00", "10:30", 21),
            ("10:30", "10:45", 7),
            ("10:45", "13:00", 30),
            ("13:00", "17:00", 21),
            ("17:00", "23:15", 22.5),
            ("23:15", "00:00", None),
        ]
        assert f(s4["living_room"]) == [
            ("00:00", "07:30", None),
            ("07:30", "23:30", 18),
            ("23:30", "00:00", None),
        ]
        assert v4 == {"var1": {"value": "06:30", "type": "default"}}

    @setup_data
    def test_get_no_name(self, tmp_path, schedule):
        (schedule.client.data / "variables.json").write_text(
            '{"var3": "14:00", "var4": "15:00"}'
        )

        all_schedules = Schedule.get(client=schedule.client)
        assert len(all_schedules) == 6
        assert len(all_schedules["Schedule 1"][0]["dining_room"]) == 5
        assert len(all_schedules["Schedule 1"][0]["bathroom"]) == 5
        assert len(all_schedules["Schedule 1"][0]["living_room"]) == 5
        assert len(all_schedules["Schedule 2"][0]["dining_room"]) == 5
        assert len(all_schedules["Schedule 2"][0]["bathroom"]) == 5
        assert len(all_schedules["Schedule 2"][0]["living_room"]) == 5
        assert all_schedules["Schedule 1"][1] == {}
        assert all_schedules["Schedule 2"][1] == {
            "var1": {"value": "09:00", "type": "default"},
            "var2": {"value": "10:00", "type": "default"},
        }
        assert all_schedules["Schedule 3"][1] == {
            "var1": {"value": "09:00", "type": "default"},
            "var2": {"value": "10:00", "type": "default"},
            "var3": {"value": "14:00", "type": "global"},
        }
        assert all_schedules["Schedule 3.1"][1] == {
            "var1": {"value": "09:30", "type": "default"},
            "var2": {"value": "10:00", "type": "default"},
            "var3": {"value": "14:00", "type": "global"},
        }
        assert all_schedules["Schedule 3.2"][1] == {
            "var1": {"value": "09:00", "type": "default"},
            "var2": {"value": "09:30", "type": "default"},
            "var3": {"value": "14:00", "type": "global"},
        }

    @setup_data
    def test_get_no_load(self, tmp_path, schedule):
        schedule_2 = Schedule.get(
            client=schedule.client, name="Schedule 2", load=False, var2="10:10"
        )
        assert schedule_2["var1"] == {"value": "09:00", "type": "default"}
        assert schedule_2["var2"] == {"value": "10:10", "type": "kwarg"}

    @setup_data
    def test_get_no_name_no_load(self, tmp_path, schedule):
        all_schedules = Schedule.get(client=schedule.client, load=False)
        assert len(all_schedules) == 6
        assert len(all_schedules["Schedule 1"]) == 0
        assert all_schedules["Schedule 2"]["var1"] == {
            "value": "09:00",
            "type": "default",
        }
        assert all_schedules["Schedule 2"]["var2"] == {
            "value": "10:00",
            "type": "default",
        }
        assert all_schedules["Schedule 3"]["var1"] == {
            "value": "09:00",
            "type": "default",
        }
        assert all_schedules["Schedule 3"]["var2"] == {
            "value": "10:00",
            "type": "default",
        }
        assert all_schedules["Schedule 3"]["var3"] == {
            "value": "global",
            "type": "default",
        }
        assert all_schedules["Schedule 3.1"]["var1"] == {
            "value": "09:30",
            "type": "default",
        }
        assert all_schedules["Schedule 3.1"]["var2"] == {
            "value": "10:00",
            "type": "default",
        }
        assert all_schedules["Schedule 3.1"]["var3"] == {
            "value": "global",
            "type": "default",
        }
        assert all_schedules["Schedule 3.2"]["var1"] == {
            "value": "09:00",
            "type": "default",
        }
        assert all_schedules["Schedule 3.2"]["var2"] == {
            "value": "09:30",
            "type": "default",
        }
        assert all_schedules["Schedule 3.2"]["var3"] == {
            "value": "global",
            "type": "default",
        }

    @setup_data
    def test_get_raises_exception(self, tmp_path, schedule):
        with pytest.raises(ValueError, match="No schedules found."):
            Schedule.get(client=schedule.client, name="Schedule A")
        with pytest.raises(
            ValueError, match="Cannot pass `kwargs` to `get` when `name` not specified."
        ):
            Schedule.get(client=schedule.client, var1="07:00")

    @setup_data
    def test_variables(self, tmp_path, schedule):
        (schedule.client.data / "variables.json").write_text(
            '{"var10": "09:00", "var20": "10:00"}'
        )
        variables = Schedule.variables(client=schedule.client)
        assert variables == {"var10": "09:00", "var20": "10:00"}

    @setup_data
    def test_variables_update(self, tmp_path, schedule):
        (schedule.client.data / "variables.json").write_text(
            '{"var10": "09:00", "var20": "10:00"}'
        )
        variables = Schedule.variables(
            client=schedule.client,
            update={"var10": "08:00", "var30": "11:00"},
        )
        assert variables == {"var10": "08:00", "var20": "10:00", "var30": "11:00"}

    @setup_data
    def test_is_active_true_1(self, tmp_path, schedule):
        (schedule.client.data / "active_schedule.json").write_text(
            json.dumps(
                {
                    "schedule": "Schedule 3.1",
                    "variables": {
                        "var1": {"value": "08:00", "type": "kwarg"},
                        "var2": {"value": "10:00", "type": "default"},
                        "var3": {"value": "12:00", "type": "global"},
                    },
                }
            )
        )
        (schedule.client.data / "variables.json").write_text(
            '{"var1": "06:00", "var3": "12:00"}'
        )
        schedule.set(refresh=True)
        assert schedule.is_active()
        assert schedule.current_variables == {
            "var1": {"value": "08:00", "type": "kwarg"},
            "var2": {"value": "10:00", "type": "default"},
            "var3": {"value": "12:00", "type": "global"},
        }

    @setup_data
    def test_is_active_true_2(self, tmp_path, schedule):
        (schedule.client.data / "active_schedule.json").write_text(
            json.dumps(
                {
                    "schedule": "Schedule 3.1",
                    "variables": {
                        "var1": {"value": "08:00", "type": "kwarg"},
                        "var2": {"value": "10:00", "type": "default"},
                        "var3": {"value": "12:00", "type": "global"},
                    },
                }
            )
        )
        (schedule.client.data / "variables.json").write_text(
            '{"var1": "06:00", "var2": "10:00", "var3": "12:00", "var4-extra": "14:00"}'
        )
        schedule.set(refresh=True)
        assert schedule.is_active()
        assert schedule.current_variables == {
            "var1": {"value": "08:00", "type": "kwarg"},
            "var2": {"value": "10:00", "type": "global"},
            "var3": {"value": "12:00", "type": "global"},
        }

    @setup_data
    def test_is_active_false_1(self, tmp_path, schedule):
        (schedule.client.data / "active_schedule.json").write_text(
            json.dumps(
                {
                    "schedule": "Schedule 3.1",
                    "variables": {
                        "var1": {"value": "08:00", "type": "kwarg"},
                        "var2": {"value": "10:00", "type": "default"},
                        "var3": {"value": "12:00", "type": "global"},
                    },
                }
            )
        )
        (schedule.client.data / "variables.json").write_text(
            '{"var1": "06:00", "var2": "11:00", "var3": "12:00"}'
        )
        schedule.set(refresh=True)
        assert not schedule.is_active()
        assert schedule.current_variables == {
            "var1": {"value": "08:00", "type": "kwarg"},
            "var2": {"value": "11:00", "type": "global"},
            "var3": {"value": "12:00", "type": "global"},
        }

    @setup_data
    def test_is_active_false_2(self, tmp_path, schedule):
        (schedule.client.data / "active_schedule.json").write_text(
            json.dumps(
                {
                    "schedule": "Schedule 3.1",
                    "variables": {
                        "var1": {"value": "08:00", "type": "kwarg"},
                        "var2": {"value": "10:00", "type": "default"},
                        "var3": {"value": "12:00", "type": "global"},
                    },
                }
            )
        )
        (schedule.client.data / "variables.json").write_text(
            '{"var1": "06:00", "var3": "13:00"}'
        )
        schedule.set(refresh=True)
        assert not schedule.is_active()
        assert schedule.current_variables == {
            "var1": {"value": "08:00", "type": "kwarg"},
            "var2": {"value": "10:00", "type": "default"},
            "var3": {"value": "13:00", "type": "global"},
        }


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


class TestSchedules:
    def test_merge_timetables_1(self):
        merged = Schedules.merge_timetables(
            [
                ("01:00", "03:00", 0),
                ("03:00", "05:00", 3),
                ("05:00", "07:00", 5),
                ("07:00", "09:00", 7),
                ("09:00", "18:00", 9),
                ("18:00", "01:00", 18),
            ],
            [
                ("02:00", "02:30", 2),
                ("02:30", "03:30", "reset"),
                ("03:30", "05:00", 22),
                ("05:00", "06:30", 33),
                ("06:30", "02:00", "reset"),
            ],
        )
        assert merged == [
            ("01:00", "02:00", 0),
            ("02:00", "02:30", 2),
            ("02:30", "03:00", 0),
            ("03:00", "03:30", 3),
            ("03:30", "05:00", 22),
            ("05:00", "06:30", 33),
            ("06:30", "07:00", 5),
            ("07:00", "09:00", 7),
            ("09:00", "18:00", 9),
            ("18:00", "01:00", 18),
        ]

    def test_merge_timetables_2(self):
        merged = Schedules.merge_timetables(
            [
                ("01:00", "03:00", 0),
                ("03:00", "05:00", 3),
                ("05:00", "07:00", 5),
                ("07:00", "09:00", 7),
                ("09:00", "18:00", 9),
                ("18:00", "01:00", 18),
            ],
            [
                ("03:00", "05:00", 2),
                ("05:00", "09:00", "reset"),
                ("09:00", "18:00", 22),
                ("18:00", "18:30", 18),
                ("18:30", "03:00", "reset"),
            ],
        )
        assert merged == [
            ("01:00", "03:00", 0),
            ("03:00", "05:00", 2),
            ("05:00", "07:00", 5),
            ("07:00", "09:00", 7),
            ("09:00", "18:00", 22),
            ("18:00", "01:00", 18),
        ]

    def test_merge_timetables_3(self):
        merged = Schedules.merge_timetables(
            [("06:00", "12:00", 0), ("12:00", "23:00", 3), ("23:00", "06:00", 1)],
            [
                ("01:00", "02:00", 2),
                ("02:00", "01:00", "reset"),
            ],
        )
        assert merged == [
            ("01:00", "02:00", 2),
            ("02:00", "06:00", 1),
            ("06:00", "12:00", 0),
            ("12:00", "23:00", 3),
            ("23:00", "01:00", 1),
        ]
