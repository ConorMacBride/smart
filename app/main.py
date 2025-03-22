import logging
from functools import lru_cache
from typing import Optional, Mapping

from fastapi import FastAPI, Security, HTTPException, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from smart import __version__
from smart.schedule import Schedule
from smart.tado import TadoClient, Presence


class Settings(BaseSettings):
    api_key: str
    tado_data: str
    tado_default_schedule: str
    tado_env: Optional[str] = None
    tado_oauth2_endpoint: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env")


app = FastAPI()

logger = logging.getLogger("uvicorn.error")

api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)


def get_api_key(api_key_header: str = Security(api_key_header)) -> str:
    settings = get_settings()
    if settings.api_key is not None and api_key_header == settings.api_key:
        return api_key_header
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API Key",
    )


@lru_cache
def get_settings():
    return Settings()


def get_client():
    settings = get_settings()
    client = TadoClient(
        data=settings.tado_data,
        env=settings.tado_env,
        oauth2_endpoint=settings.tado_oauth2_endpoint,
        logger=logger,
    )
    return client


@app.get("/")
async def root(api_key: str = Security(get_api_key)):
    return {"version": __version__}


@app.post("/tado/home")
async def home(api_key: str = Security(get_api_key)):
    client = get_client()
    client.set_home()
    if client.get_presence() != Presence.HOME:
        raise HTTPException(500, "Failed to update presence.")
    return {"presence": Presence.HOME}


@app.post("/tado/away")
async def away(api_key: str = Security(get_api_key)):
    client = get_client()
    client.set_away()
    if client.get_presence() != Presence.AWAY:
        raise HTTPException(500, "Failed to update presence.")
    return {"presence": Presence.AWAY}


@app.post("/tado/schedule/reset")
async def reset(api_key: str = Security(get_api_key)):
    settings = get_settings()
    client = get_client()
    schedule = Schedule(client=client)
    schedule.set(settings.tado_default_schedule)
    schedule.push()
    variables = {k: v["value"] for k, v in schedule.current_variables.items()}
    return {"schedule": schedule.current_schedule, "variables": variables}


@app.get("/tado/schedule/active")
async def active(api_key: str = Security(get_api_key)):
    client = get_client()
    schedule = Schedule(client=client)
    active_schedule, variables = schedule.active_schedule
    return {
        "schedule": active_schedule,
        "variables": variables,
    }


@app.get("/tado/schedule/all")
async def all_schedules(api_key: str = Security(get_api_key)):
    client = get_client()
    schedules = Schedule.get(client=client, load=False)
    return {k: {kk: vv["value"] for kk, vv in v.items()} for k, v in schedules.items()}


class ScheduleConfig(BaseModel):
    name: str | None = None
    variables: Mapping = Field(default_factory=dict)


@app.post("/tado/schedule/set")
async def set_schedule(config: ScheduleConfig, api_key: str = Security(get_api_key)):
    client = get_client()
    schedule = Schedule(client=client)
    schedule.set(config.name, **config.variables)
    schedule.push()
    variables = {k: v["value"] for k, v in schedule.current_variables.items()}
    return {"schedule": schedule.current_schedule, "variables": variables}


@app.get("/tado/schedule/variables")
async def get_schedule_variables(api_key: str = Security(get_api_key)):
    client = get_client()
    return Schedule.variables(client=client)


@app.post("/tado/schedule/variables")
async def set_schedule_variables(
    variables: Mapping, api_key: str = Security(get_api_key)
):
    client = get_client()
    variables = Schedule.variables(client=client, update=variables)
    schedule = Schedule(client=client)
    schedule.set(refresh=True)
    if not schedule.is_active():
        schedule.push()
    return variables
