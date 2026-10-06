# award-local — 상장·표창장·감사장 생성기

> **한 줄 요약** — 디자인(7종)을 고르고 상훈·수상자·수여 기관을 입력하면 A4 상장을 실시간 미리보기로 보여 주고, 인쇄용 PDF·PNG(300dpi)로 내려받는 도구입니다.
> 상훈 종류별 기본 수상 문구 5~6개 중 고르거나 직접 쓰고, 로컬 LLM이 있으면 직접 쓴 문구를 상장 문체로 다듬습니다(선택).
> 수상자 목록(엑셀 붙여넣기·CSV·xlsx)으로 일괄 발급(번호 자동 증가), 발급 이력은 WORKSPACE 에 남습니다.
> 나눔명조·나눔고딕(OFL)을 동봉했고, 테두리·메달·한지 질감·직인은 코드로 그립니다. CDN·외부 통신 없음.

```bash
bash setup.sh                 # Python → Pillow(없으면 venv) → LLM 탐색(선택) → selftest → http://localhost:8779
bash setup.sh stop
python3 app.py                # 수동 실행
python3 app.py --cli cfg.json out.pdf     # 설정 JSON 으로 한 장 (out.png 이면 PNG)
python3 selftest.py           # LLM 없이 검증 (WORKSPACE 를 임시 폴더로 바꿔 돌고 지움)
```

| 환경변수 | 기본 | 설명 |
|---|---|---|
| `PORT` | `8779` | |
| `WORKSPACE` | `./_workspace` | 발급 이력 `history.jsonl`, 발급본 `issued/*.pdf`, 올린 로고·직인 `uploads/` |
| `LLM_API` / `LLM_BASE_URL` / `LLM_MODEL` | `ollama` / `http://localhost:11434` / `qwen3:8b` | '상장 문체로 다듬기'에만 씀. 없으면 그 버튼만 꺼짐 |

구성: `render.py`(Pillow 렌더러 — 미리보기·PNG·PDF 가 같은 그림), `phrases.py`(종류별 기본 문구), `app.py`(stdlib HTTP), `ui.html`.

디자인: 전통 금색 테두리(뇌문 띠) · 청색 공문형 · 모던 미니멀 · 한지 질감 · 리본·메달형 · 흰 바탕 금테(금속 광택 이중 테두리) · 모서리 금띠(모서리만 대각선 금띠, 네 모서리 또는 왼위·오른아래 두 모서리). A4 세로/가로.
직인: 기관명 글자로 자동 생성(사각·원형, 글자 바꾸기 가능) 또는 이미지 업로드(흰 바탕은 투명 처리).
PDF 는 300dpi 이미지 PDF 입니다(글자 선택·검색 안 됨). 인쇄 시 배율 100%.

폐쇄망: 폴더를 통째로 복사. Pillow 가 없는 서버면 `wheels/` 에 pillow 휠을 넣어 두면 오프라인 설치.

## 출처·감사 (Credits)

- 동봉: 나눔명조·나눔고딕 (Copyright (c) 2010 NHN Corporation, SIL Open Font License 1.1, `static/fonts/OFL.txt`) — 출처 [google/fonts](https://github.com/google/fonts/tree/main/ofl)
- [Pillow](https://github.com/python-pillow/Pillow) (HPND) — 렌더링 (pip 의존성, 동봉 안 함)
- 테두리·문양·직인은 모두 코드로 그립니다. 실존 기관의 로고·직인은 들어 있지 않습니다.
- **LLM 실행** — OpenAI 호환 API 로 호출합니다(모델 가중치는 동봉하지 않음). 기본 배포는 [Ollama](https://github.com/ollama/ollama) (MIT) 위의 Google [Gemma](https://ai.google.dev/gemma) `gemma4:31b` — 모델 이용 조건은 Gemma 배포처 참고.
- 이 도구는 [agent-page-portal](https://github.com/gggg8657/agent-page-portal) 에 연결해 쓰도록 만들었습니다(단독 실행도 됨).

저작권 표기·전체 목록은 `NOTICE` 를 보세요.
