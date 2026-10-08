# MES AI Edge Gateway

공장 현장의 PLC(Modbus TCP)와 MES(MQTT)를 잇는 프로토콜 브리지. 설비 제어/상태 경로만 담당합니다.

- 센서 데이터는 센서가 브로커로 직접 발행하고 MES·AI가 구독하므로 게이트웨이를 거치지 않습니다.
- 게이트웨이 한 대가 여러 PLC를 동시에 폴링합니다(`MACHINES`).

```
MES Backend ──mes/machines/{code}/job (retained)──▶ Edge Gateway ──Modbus write──▶ PLC
MES Backend ◀──mes/machines/{code}/state, events── Edge Gateway ◀──Modbus read─── PLC
```

## 동작: 목표 상태 맞추기(reconcile)

MES가 발행한 목표 작업(`job`)과 PLC 상태를 `POLL_INTERVAL`마다 비교합니다.

| PLC 상태 | MES 목표 | 동작 |
| --- | --- | --- |
| COMPLETE | 같은 작업 | `job_completed` 이벤트 보고 (3초마다 재보고, MES는 멱등 처리) |
| COMPLETE | 다른 작업/없음 | `RESET` (MES가 완료를 반영함) |
| RUNNING | 없음 (정지/HOLD) | `STOP` |
| 그 외 | 있음 | `START(작업, 목표수량, 이어서 가공할 수량)` |

이어서 가공할 수량은 MES의 `producedQty`와 게이트웨이가 마지막으로 읽은 PLC 수량 중 큰 값입니다.
명령이 아니라 목표 상태를 맞추는 방식이라 게이트웨이·PLC·MES 중 무엇이 재시작돼도 다음 주기에 같은 상태로 돌아옵니다.
MES 목표를 아직 받지 못한 상태(기동 직후)에서는 PLC를 건드리지 않습니다.

## MQTT 토픽

| 토픽 | 방향 | QoS | 내용 |
| --- | --- | --- | --- |
| `mes/machines/{code}/job` | 구독 | 1, retained | `{"job": {...} \| null}` |
| `mes/machines/{code}/state` | 발행 | 0 | `{"plcOnline", "state", "workOrderId", "producedQty", "targetQty", "alarmCode", "spindleRpm"}`, 변화 시 또는 `STATE_PUBLISH_INTERVAL`마다 |
| `mes/machines/{code}/events` | 발행 | 1 | `{"type": "job_completed", "workOrderId", "producedQty"}` |
| `mes/gateways/{id}/status` | 발행 | 1, retained | `online` / `offline`(LWT) |

PLC와 통신이 끊기면 `{"plcOnline": false}`를 발행하고, 복구되면 그대로 reconcile을 재개합니다.

## Modbus 레지스터 맵

`gateway/registers.py`는 [mes-ai-machine-emulator](https://github.com/ljs3536/mes-ai-machine-emulator)와 같은 파일입니다.
명령 블록 0~5(CMD, JOB_ID, TARGET, START_QTY, CMD_SEQ), 상태 블록 100~108을 사용하며 자세한 내용은 에뮬레이터 README를 참고하세요.

## 설정

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `GATEWAY_ID` | `edge-gw-01` | 게이트웨이 식별자 |
| `MACHINES` | | `CODE=host:port[/unitId]`, 쉼표 구분 |
| `MQTT_HOST` / `MQTT_PORT` | `localhost` / `1883` | 브로커 |
| `POLL_INTERVAL` | `0.5` | PLC 폴링 주기(초) |
| `STATE_PUBLISH_INTERVAL` | `1.0` | 상태가 같을 때 재발행 주기(초) |
| `MODBUS_TIMEOUT` | `2.0` | Modbus 응답 대기(초) |

## 실행

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/python -m gateway
```

컨테이너:

```bash
docker build -t factory-mes/edge-gateway .
docker run -e MACHINES=MACHINE_A=<plc-a>:5020,MACHINE_B=<plc-b>:5020 -e MQTT_HOST=<broker> factory-mes/edge-gateway
```

## 확장 예정

- 간단한 안전 인터록(예: 브로커 단절 시에도 온도 임계치 초과면 로컬 STOP)
- MQTT 인증/TLS, 브로커 단절 시 상태 버퍼링
