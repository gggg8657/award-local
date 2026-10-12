# 제3자 구성요소 고지 (THIRD_PARTY_NOTICES)

award-local 의 원저작물은 DongJu Kim(gggg8657)이 작성했습니다(`NOTICE`, `LICENSE`). 아래 제3자 구성요소는 각자의 라이선스를 따르며, 이 저장소의 MIT 라이선스로 바뀌지 않습니다.
조사일: 2026-10-12 (실제 파일·설치 메타데이터 기준). "상업 이용" 칸은 확인한 라이선스 문구를 요약한 것이며 법률 판단이 아닙니다.

| 이름 | 버전 | 쓰임 | 라이선스 | 링크 | 상업 이용 | 비고 |
|---|---|---|---|---|---|---|
| 나눔명조 (Regular/Bold/ExtraBold) | — | **동봉** `static/fonts/NanumMyeongjo-*.ttf` | SIL OFL 1.1 | [google/fonts ofl/nanummyeongjo](https://github.com/google/fonts/tree/main/ofl/nanummyeongjo) | 가능 | Copyright (c) 2010 NHN Corporation. 원문 `static/fonts/OFL.txt` 동봉. 글꼴 단독 판매 금지, 예약 글꼴 이름(Nanum…) 변경본 사용 금지 |
| 나눔고딕 (Regular/Bold/ExtraBold) | — | **동봉** `static/fonts/NanumGothic-*.ttf` | SIL OFL 1.1 | [google/fonts ofl/nanumgothic](https://github.com/google/fonts/tree/main/ofl/nanumgothic) | 가능 | 위와 같음 |
| Pillow | `>=9.2` (확인 환경 12.1.1) | 설치 (`requirements.txt`) | MIT-CMU (HPND 계열) | [python-pillow/Pillow](https://github.com/python-pillow/Pillow) | 가능 | 동봉 안 함 |
| Python 표준 라이브러리 | 3.x | 실행 환경 | PSF-2.0 | [python.org](https://docs.python.org/3/license.html) | 가능 | |
| Ollama | — | 외부 서비스 (LLM 서버, 선택) | MIT | [ollama/ollama](https://github.com/ollama/ollama) | 가능 | 동봉 안 함. LLM 없이도 동작(문구 다듬기만 꺼짐) |
| Google Gemma 4 `gemma4:31b` | — | 외부 서비스가 돌리는 모델 (기본 배포) | Apache-2.0 | [google/gemma-4-31B-it](https://huggingface.co/google/gemma-4-31B-it) | 가능 | 가중치 동봉 안 함. `LLM_MODEL` 로 다른 모델 지정 가능 |

## 코드로 그린 요소

테두리·뇌문·메달·한지 질감·직인 그림은 모두 `render.py` 코드로 그립니다. 실존 기관의 로고·직인·상징은 들어 있지 않습니다 — 사용자가 올린 파일만 쓰며, 그 파일의 권리는 올린 사람에게 있습니다.

## 확인 필요

없음 (2026-10-12 조사 기준). 새 구성요소를 넣으면 이 표와 `NOTICE` 를 함께 갱신하세요.
