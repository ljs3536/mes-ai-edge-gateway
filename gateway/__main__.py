import asyncio
import logging

from .config import Settings
from .machine_link import MachineLink
from .mqtt_link import MqttLink
from .plc_client import PlcClient


async def run(settings: Settings) -> None:
    mqtt = MqttLink(settings)
    mqtt.start()
    links = [MachineLink(PlcClient(m, settings.modbus_timeout), mqtt, settings) for m in settings.machines]
    logging.getLogger("gateway").info(
        "%s 시작 · MQTT %s:%d · PLC %s",
        settings.gateway_id, settings.mqtt_host, settings.mqtt_port,
        ", ".join(f"{m.code}={m.host}:{m.port}" for m in settings.machines),
    )
    try:
        while True:
            await asyncio.gather(*(link.poll() for link in links))
            await asyncio.sleep(settings.poll_interval)
    finally:
        for link in links:
            link.plc.close()
        mqtt.stop()


def main() -> None:
    settings = Settings()
    logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("pymodbus").setLevel(logging.CRITICAL)
    try:
        asyncio.run(run(settings))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
