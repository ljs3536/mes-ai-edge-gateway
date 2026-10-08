"""MES 쪽 MQTT 연결. 설비별 목표 작업(retained)을 구독하고 상태/이벤트를 publish 한다.

Topic
- mes/machines/{code}/job     (MES → GW, retained, QoS1) {"job": {...} | null}
- mes/machines/{code}/state   (GW → MES, QoS0)            PLC 상태 스냅샷
- mes/machines/{code}/events  (GW → MES, QoS1)            job_completed 등
- mes/gateways/{id}/status    (GW, retained, LWT)          online / offline
"""

import json
import logging
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

import paho.mqtt.client as mqtt

from .config import Settings

log = logging.getLogger("gateway.mqtt")

_UNKNOWN = object()


def now_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="milliseconds")


class MqttLink:
    def __init__(self, settings: Settings):
        self.prefix = settings.mqtt_topic_prefix
        self.codes = [m.code for m in settings.machines]
        self.status_topic = f"{self.prefix}/gateways/{settings.gateway_id}/status"
        self._desired: dict[str, object] = {code: _UNKNOWN for code in self.codes}
        self._lock = threading.Lock()

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=settings.gateway_id)
        self.client.will_set(self.status_topic, "offline", qos=1, retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = lambda *_: log.warning("MQTT 연결 끊김, 재연결 대기")
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(1, 30)
        self.client.connect_async(settings.mqtt_host, settings.mqtt_port, keepalive=30)

    def start(self) -> None:
        self.client.loop_start()

    def stop(self) -> None:
        self.client.publish(self.status_topic, "offline", qos=1, retain=True).wait_for_publish(2)
        self.client.loop_stop()
        self.client.disconnect()

    def topic(self, code: str, kind: str) -> str:
        return f"{self.prefix}/machines/{code}/{kind}"

    def _on_connect(self, client, _userdata, _flags, reason_code, _props):
        if reason_code.is_failure:
            log.error("MQTT 연결 거부: %s", reason_code)
            return
        client.subscribe([(self.topic(code, "job"), 1) for code in self.codes])
        client.publish(self.status_topic, "online", qos=1, retain=True)
        log.info("MQTT 연결됨, 목표 작업 구독: %s", ", ".join(self.codes))

    def _on_message(self, _client, _userdata, msg):
        code = msg.topic.split("/")[-2]
        try:
            job = json.loads(msg.payload).get("job") if msg.payload else None
        except (ValueError, AttributeError):
            log.warning("잘못된 job 메시지 %s: %r", msg.topic, msg.payload[:200])
            return
        with self._lock:
            self._desired[code] = job
        log.info("%s 목표 작업 → %s", code, f"{job['woNo']} ({job['producedQty']}/{job['quantity']})" if job else "없음")

    def desired_job(self, code: str) -> tuple[bool, dict | None]:
        """(목표를 수신했는지, 목표 작업). 수신 전에는 설비를 건드리지 않는다."""
        with self._lock:
            value = self._desired[code]
        if value is _UNKNOWN:
            return False, None
        return True, value  # type: ignore[return-value]

    def publish_state(self, code: str, state: dict) -> None:
        self.client.publish(self.topic(code, "state"), json.dumps({"ts": now_iso(), **state}), qos=0)

    def publish_event(self, code: str, event: dict) -> None:
        self.client.publish(self.topic(code, "events"), json.dumps({"ts": now_iso(), **event}), qos=1)
