import logging
import time

from .config import Settings
from .mqtt_link import MqttLink
from .plc_client import PlcClient, PlcError, PlcStatus
from .registers import Command, PlcState

log = logging.getLogger("gateway.machine")

COMPLETE_REPORT_INTERVAL = 3.0


class MachineLink:
    """PLC 1대 ↔ MES 연동.

    MES가 retained로 내려준 목표 작업(desired)과 PLC 실제 상태를 매 주기 비교해 맞춘다(reconcile).
    게이트웨이/PLC가 재시작되어도 다음 주기에 같은 상태로 수렴한다.
    """

    def __init__(self, client: PlcClient, mqtt: MqttLink, settings: Settings):
        self.plc = client
        self.mqtt = mqtt
        self.code = client.endpoint.code
        self.state_interval = settings.state_publish_interval
        self._last_state: dict | None = None
        self._last_state_at = 0.0
        self._last_complete_report: tuple[int, float] = (0, 0.0)
        self._produced_by_job: dict[int, int] = {}
        self._online = True

    async def poll(self) -> None:
        try:
            status = await self.plc.read_status()
        except PlcError as e:
            if self._online:
                log.warning("%s PLC 통신 실패: %s", self.code, e)
            self._online = False
            self._publish_state({"plcOnline": False})
            return

        if not self._online:
            log.info("%s PLC 통신 복구", self.code)
        self._online = True
        try:
            await self._reconcile(status)
        except PlcError as e:
            log.warning("%s 명령 전송 실패: %s", self.code, e)
        self._publish_state(
            {
                "plcOnline": True,
                "state": status.state.name,
                "workOrderId": status.job_id or None,
                "producedQty": status.produced_qty,
                "targetQty": status.target_qty,
                "alarmCode": status.alarm_code,
                "spindleRpm": status.spindle_rpm,
            }
        )

    async def _reconcile(self, st: PlcStatus) -> None:
        if st.job_id and st.state != PlcState.IDLE:
            self._produced_by_job[st.job_id] = max(self._produced_by_job.get(st.job_id, 0), st.produced_qty)

        known, job = self.mqtt.desired_job(self.code)
        if not known:
            return
        want = job["workOrderId"] if job else None
        self._produced_by_job = {k: v for k, v in self._produced_by_job.items() if k == want or k == st.job_id}

        if st.state == PlcState.COMPLETE:
            if want == st.job_id:
                self._report_complete(st)
            else:
                log.info("%s 완료 처리 확인됨 → PLC RESET", self.code)
                await self.plc.send(Command.RESET)
            return

        if job is None:
            if st.state == PlcState.RUNNING:
                log.info("%s MES 목표 없음 → PLC STOP (job=%d)", self.code, st.job_id)
                await self.plc.send(Command.STOP)
            return

        if st.state == PlcState.RUNNING and st.job_id == want:
            return
        # PLC가 재시작되면 카운터가 0이 되므로 MES/게이트웨이가 아는 가장 큰 수량부터 이어서 가공한다.
        start_qty = max(job["producedQty"], self._produced_by_job.get(want, 0))
        log.info("%s PLC START %s %d/%d", self.code, job["woNo"], start_qty, job["quantity"])
        await self.plc.send(Command.START, want, job["quantity"], start_qty)

    def _report_complete(self, st: PlcStatus) -> None:
        last_job, last_at = self._last_complete_report
        now = time.monotonic()
        if last_job == st.job_id and now - last_at < COMPLETE_REPORT_INTERVAL:
            return
        self.mqtt.publish_event(
            self.code, {"type": "job_completed", "workOrderId": st.job_id, "producedQty": st.produced_qty}
        )
        self._last_complete_report = (st.job_id, now)
        log.info("%s 작업 완료 보고 job=%d %d/%d", self.code, st.job_id, st.produced_qty, st.target_qty)

    def _publish_state(self, state: dict) -> None:
        now = time.monotonic()
        if state == self._last_state and now - self._last_state_at < self.state_interval:
            return
        self.mqtt.publish_state(self.code, state)
        self._last_state, self._last_state_at = state, now
