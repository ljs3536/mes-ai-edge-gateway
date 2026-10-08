from dataclasses import dataclass

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from . import registers as reg
from .config import MachineEndpoint
from .registers import Command, PlcState


class PlcError(Exception):
    pass


@dataclass(frozen=True)
class PlcStatus:
    state: PlcState
    job_id: int
    produced_qty: int
    target_qty: int
    alarm_code: int
    spindle_rpm: int
    heartbeat: int
    ack_seq: int

    @classmethod
    def from_words(cls, w: list[int]) -> "PlcStatus":
        return cls(
            state=PlcState(w[0]),
            job_id=reg.join_u32(w[1], w[2]),
            produced_qty=w[3],
            target_qty=w[4],
            alarm_code=w[5],
            spindle_rpm=w[6],
            heartbeat=w[7],
            ack_seq=w[8],
        )


class PlcClient:
    """Modbus TCP로 PLC 상태 블록을 읽고 명령 블록을 쓴다."""

    def __init__(self, endpoint: MachineEndpoint, timeout: float):
        self.endpoint = endpoint
        self._client = AsyncModbusTcpClient(endpoint.host, port=endpoint.port, timeout=timeout, retries=0)
        self._seq = 0

    async def _ensure_connected(self) -> None:
        if not self._client.connected and not await self._client.connect():
            raise PlcError(f"{self.endpoint.host}:{self.endpoint.port} 연결 실패")

    async def read_status(self) -> PlcStatus:
        await self._ensure_connected()
        try:
            res = await self._client.read_holding_registers(
                reg.ST_STATE, count=reg.ST_BLOCK_SIZE, device_id=self.endpoint.device_id
            )
        except ModbusException as e:
            raise PlcError(str(e)) from e
        if res.isError():
            raise PlcError(f"상태 읽기 실패: {res}")
        status = PlcStatus.from_words(res.registers)
        if self._seq == 0:
            self._seq = status.ack_seq
        return status

    async def send(self, command: Command, job_id: int = 0, target_qty: int = 0, start_qty: int = 0) -> None:
        await self._ensure_connected()
        self._seq = (self._seq % 0xFFFF) + 1
        words = [int(command), *reg.split_u32(job_id), target_qty, start_qty, self._seq]
        try:
            res = await self._client.write_registers(reg.CMD_CODE, words, device_id=self.endpoint.device_id)
        except ModbusException as e:
            raise PlcError(str(e)) from e
        if res.isError():
            raise PlcError(f"명령 쓰기 실패: {res}")

    def close(self) -> None:
        self._client.close()
