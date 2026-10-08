from dataclasses import dataclass

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from typing import Annotated


@dataclass(frozen=True)
class MachineEndpoint:
    code: str
    host: str
    port: int
    device_id: int = 1


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gateway_id: str = "edge-gw-01"
    machines: Annotated[list[MachineEndpoint], NoDecode] = [MachineEndpoint("MACHINE_A", "localhost", 5020)]
    """`MACHINE_A=host:port,MACHINE_B=host:port[/device_id]` 형식."""

    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_topic_prefix: str = "mes"

    poll_interval: float = 0.5
    state_publish_interval: float = 1.0
    modbus_timeout: float = 2.0

    log_level: str = "INFO"

    @field_validator("machines", mode="before")
    @classmethod
    def parse_machines(cls, value):
        if not isinstance(value, str):
            return value
        endpoints = []
        for item in filter(None, (v.strip() for v in value.split(","))):
            code, _, addr = item.partition("=")
            addr, _, device = addr.partition("/")
            host, _, port = addr.rpartition(":")
            endpoints.append(MachineEndpoint(code.strip(), host, int(port), int(device or 1)))
        return endpoints
