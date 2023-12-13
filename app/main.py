from functools import lru_cache
from typing import Optional

from fastapi import FastAPI, Security, HTTPException, status
from fastapi.security import APIKeyHeader
from pydantic_settings import BaseSettings, SettingsConfigDict

from smart import __version__
from smart.tado import TadoClient, Presence


class Settings(BaseSettings):
    api_key: str
    tado_username: str
    tado_password: str
    tado_env: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env")


app = FastAPI()

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
        username=settings.tado_username,
        password=settings.tado_password,
        env=settings.tado_env,
    )
    return client


@app.get("/")
async def root(api_key: str = Security(get_api_key)):
    return {"version": __version__}


@app.get("/tado/home")
async def home(api_key: str = Security(get_api_key)):
    client = get_client()
    client.set_home()
    if client.get_presence() != Presence.HOME:
        raise HTTPException(500, "Failed to update presence.")


@app.get("/tado/away")
async def away(api_key: str = Security(get_api_key)):
    client = get_client()
    client.set_away()
    if client.get_presence() != Presence.AWAY:
        raise ValueError(500, "Failed to update presence.")
