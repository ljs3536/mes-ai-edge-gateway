"""PLC Modbus 레지스터 맵. mes-ai-machine-emulator의 emulator/registers.py와 동일하게 유지한다.

모든 값은 holding register(FC3 읽기 / FC16 쓰기)이며 16bit 부호 없는 정수다.
32bit 값은 상위 워드가 먼저 온다(big-endian word order).
"""

from enum import IntEnum

# 명령 블록: 게이트웨이가 쓴다. CMD_SEQ가 바뀌면 PLC가 명령을 1회 처리한다.
CMD_CODE = 0
CMD_JOB_ID_HI = 1
CMD_JOB_ID_LO = 2
CMD_TARGET_QTY = 3
CMD_START_QTY = 4
CMD_SEQ = 5
CMD_BLOCK_SIZE = 6

# 상태 블록: PLC가 갱신하고 게이트웨이가 읽는다.
ST_STATE = 100
ST_JOB_ID_HI = 101
ST_JOB_ID_LO = 102
ST_PRODUCED_QTY = 103
ST_TARGET_QTY = 104
ST_ALARM_CODE = 105
ST_SPINDLE_RPM = 106
ST_HEARTBEAT = 107
ST_ACK_SEQ = 108
ST_BLOCK_SIZE = 9

REGISTER_COUNT = 200


class Command(IntEnum):
    NONE = 0
    START = 1
    STOP = 2
    RESET = 3


class PlcState(IntEnum):
    IDLE = 0
    RUNNING = 1
    STOPPED = 2
    COMPLETE = 3
    ALARM = 4


def split_u32(value: int) -> tuple[int, int]:
    return (value >> 16) & 0xFFFF, value & 0xFFFF


def join_u32(hi: int, lo: int) -> int:
    return (hi << 16) | lo
