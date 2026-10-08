"""PLC와 MES 사이의 제어 브리지.

현재 기능:
- MES가 내려 둔 작업(retained)을 읽고 Modbus TCP로 PLC를 그 상태에 맞춤
- PLC의 진행 수량과 상태를 MQTT로 MES에 보고
- PLC가 재시작되면 MES 수량과 PLC 수량 중 큰 값으로 이어서 진행
센서 파형 수집은 하지 않는다. 파형은 센서 에뮬레이터가 브로커로 직접 보낸다.
"""

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
