# NAVER WORKS Bot 알림 트리거 — 날인요청

`backend/app/routers/seal_requests.py` 의 `_bot_send` 호출 지점을 정리한 명세.
실제 메시지가 도달하려면 받는 사람의 `User.works_user_id` 또는 `User.email` 이 채워져 있어야 함.

## 알림 매트릭스

| # | 트리거 | 받는 사람 | 메시지 | 비고 |
|---|---|---|---|---|
| 1 | **날인요청 등록** (요청자 `member`) | 같은 팀의 team_lead 1명 | `[날인요청] {프로젝트} - {seal_type} ({title})` | 팀장 못 찾으면 admin 전원으로 fallback |
| 2 | **날인요청 등록** (요청자 `team_lead` 또는 `admin`) | admin 전원 (본인 포함) | 동일 | 본인이 admin이라도 본인에게도 발송 |
| 3 | **1차 승인** (팀장이 1차검토 통과) | admin 전원 (본인 포함) | `[2차검토 요청] {title}` + 1차검토자/요청자/제출예정일 | 본인이 admin이라도 본인에게도 발송 |
| 4 | **최종 승인** (admin이 2차검토 통과) | 요청자 | `[승인 완료] {title} / 처리자` | 연결 TASK는 자동으로 '완료'로 동기 |
| 5 | **반려** (1차 또는 2차에서 반려) | 요청자 | `[반려] {title} / 사유 / 처리자` | 반려사유는 노션 페이지에도 저장 |
| 6 | **재요청** (반려된 요청을 수정 후 재제출) | 등록과 동일 라우팅 (1·2번) | `[날인 재요청] {title}` | 상태가 자동으로 1차검토 중으로 복구 |

> 폴더 검증(폴더 비어있을 때) 알림은 운영 결정으로 **제거됨**. 등록 모달에서 사용자가 사전에 확인 가능.

## 발송 메커니즘

- `_bot_send(works_user_id, text)` — fire-and-forget. 실패해도 endpoint 응답에 영향 없음.
- `_resolve_works_id(user)` 우선순위: `works_user_id` → `email`. 둘 다 비면 silent skip.
- `sso_works_bot.send_text` 가 NAVER WORKS Bot API (`POST /bots/{bot_id}/users/{user_id}/messages`) 호출.

## 받는 사람 결정 함수

- **`_find_team_lead(db, requester_name)`**: 요청자 이름 → `Employee.team` → 같은 팀의 `team_lead` role User 1명. 없으면 None.
- **`_find_admins(db)`**: `User.role == "admin"` 인 active 사용자 전원.
- **`_find_user_by_name(db, name)`**: 이름으로 active 사용자 1명 (요청자 본인 찾을 때).

## 동작 확인 체크리스트

1. Render env에 다음이 설정되어 있는지:
   ```
   WORKS_BOT_ENABLED=true
   WORKS_BOT_ID=<발급된 Bot ID>
   WORKS_BOT_SERVICE_ACCOUNT_ID=...
   WORKS_BOT_PRIVATE_KEY=<PEM 전체>
   ```
2. 받는 사람의 `User.works_user_id` 또는 `email` 이 채워졌는지.
3. Render Logs에서 `sso_works_bot` 키워드로 추적.

## 관련 코드

- 등록 / 재요청: `backend/app/routers/seal_requests.py` `create_seal_request`, `update_seal_request`
- 승인: `approve_lead`, `approve_admin`
- 반려: `reject_seal_request`
- helpers: `_bot_send`, `_resolve_works_id`, `_find_team_lead`, `_find_admins`
