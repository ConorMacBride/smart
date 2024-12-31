import pytest

from smart.schedule_utils import ScheduleVariables, parse_dynamic_times


def test_parse_dynamic_times_raises_exception():
    with pytest.raises(KeyError):
        parse_dynamic_times([{"time": "{var2}"}])
    for time in ["{var1|01:00}", "{var1|+1:00}", "{var1|-1:00}"]:
        with pytest.raises(ValueError, match="not a valid dynamic format"):
            parse_dynamic_times([{"time": time}], var1="07:00")
    for time in ["aaa", "7:00", "0700"]:
        with pytest.raises(ValueError, match="not a valid static format"):
            parse_dynamic_times([{"time": time}])


class TestScheduleVariables:
    def test_add_default(self):
        sv = ScheduleVariables()
        sv.add_default(var1="07:00")
        ex = {"var1": {"type": "default", "value": "07:00"}}
        assert sv == ex
        assert sv == ScheduleVariables(ex)

    def test_add_global(self):
        sv = ScheduleVariables()
        sv.add_global(var1="07:00")
        ex = {"var1": {"type": "global", "value": "07:00"}}
        assert sv == ex
        assert sv == ScheduleVariables(ex)

    def test_add_kwarg(self):
        sv = ScheduleVariables()
        sv.add_kwarg(var1="07:00")
        ex = {"var1": {"type": "kwarg", "value": "07:00"}}
        assert sv == ex
        assert sv == ScheduleVariables(ex)

    def test_set_raises(self):
        sv = ScheduleVariables()
        with pytest.raises(NotImplementedError):
            sv["var1"] = "07:00"

    def test_get(self):
        sv = ScheduleVariables()
        sv.add_default(var1="07:00")
        assert sv["var1"] == "07:00"
        with pytest.raises(KeyError):
            sv["var2"]

    def test_eq(self):
        sv1 = ScheduleVariables()
        sv1.add_default(var1="07:00")
        sv2 = ScheduleVariables()
        sv2.add_default(var1="07:00")
        assert sv1 == sv2
        assert sv1 == {"var1": "07:00"}
        assert sv1 != {"var1": "07:01"}
        assert sv1 != {"var2": "07:00"}
        assert sv1 != {"var1": "07:00", "var2": "07:00"}
        assert sv1 != {"var1": "07:00", "var2": "07:00"}
        sv1.add_default(var2="08:00")
        assert sv1 != sv2
        sv2.add_default(var2="08:00")
        assert sv1 == sv2
        assert sv1.data == sv2.data
        sv2.add_global(var2="08:00")
        assert sv1 == sv2
        assert sv1.data != sv2.data
        sv2.add_global(var2="09:00")
        assert sv1 != sv2
        sv2.add_kwarg(var1="06:00", var2="10:00")
        assert sv2.data == {
            "var1": {"type": "kwarg", "value": "06:00"},
            "var2": {"type": "kwarg", "value": "10:00"},
        }
        sv2.add_global(var2="07:00")
        assert sv2["var2"] == "10:00"
        sv2.add_default(var2="07:00")
        assert sv2["var2"] == "10:00"
        sv2.add_kwarg(var2="07:00")
        assert sv2["var2"] == "07:00"
