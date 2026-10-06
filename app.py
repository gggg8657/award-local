#!/usr/bin/env python3
"""award local — 상장·표창장·감사장 생성기. Pillow 로 A4 를 그려 PDF/PNG(300dpi). CDN 없음, 폰트 동봉(나눔명조·나눔고딕, OFL).

  python3 app.py                       # http://localhost:8779
  python3 app.py --cli cfg.json out.pdf   # 설정 JSON 으로 한 장 (LLM 불필요)
LLM(선택): 직접 쓴 문구를 상장 문체로 다듬기 — LLM_API=ollama|openai, LLM_BASE_URL, LLM_MODEL
"""
import base64
import csv
import datetime
import hashlib
import io
import json
import os
import re
import secrets
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image

import phrases
import render

ROOT = os.path.dirname(os.path.abspath(__file__))
WS = os.environ.get("WORKSPACE") or os.path.join(ROOT, "_workspace")  # 포털이 AGENT_DATA/<도구> 로 모아 줌
LLM_API = os.environ.get("LLM_API", "ollama")            # ollama | openai (vLLM·LM Studio·llama.cpp 등)
LLM_BASE = os.environ.get("LLM_BASE_URL", "http://localhost:8000/v1" if LLM_API == "openai" else "http://localhost:11434").rstrip("/")
MODEL = os.environ.get("LLM_MODEL", "qwen3:8b")
LLM_KEY = os.environ.get("LLM_API_KEY", "")
PORT = int(os.environ.get("PORT", "8779"))
DPI = 300
PREVIEW_DPI = 90
MAX_BATCH = 300
LOCK = threading.Lock()


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def ws(*p):
    d = os.path.join(WS, *p[:-1]) if len(p) > 1 else WS
    os.makedirs(d, exist_ok=True)
    return os.path.join(WS, *p)


# ── 번호 ────────────────────────────────────────────────────────────────
def bump(num, k=1):
    """번호의 마지막 숫자 덩어리를 k 만큼 올린다(자리수 유지): 2026-009 → 2026-010, 제 7 호 → 제 8 호"""
    m = list(re.finditer(r"\d+", num or ""))
    if not m:
        return num
    g = m[-1]
    return num[:g.start()] + str(int(g.group()) + k).zfill(len(g.group())) + num[g.end():]


def next_number(year=None):
    """올해 발급 이력의 'YYYY-NNN' 최댓값 + 1"""
    year = year or datetime.date.today().year
    top = 0
    for h in history():
        m = re.search(rf"{year}-(\d+)", h.get("number") or "")
        if m:
            top = max(top, int(m.group(1)))
    return f"{year}-{top + 1:03d}"


# ── 이력 ────────────────────────────────────────────────────────────────
def history(limit=None):
    p = os.path.join(WS, "history.jsonl")
    if not os.path.exists(p):
        return []
    out = []
    for line in read(p).splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    out.reverse()
    return out[:limit] if limit else out


def log_issue(recs):
    with LOCK, open(ws("history.jsonl"), "a", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# ── 업로드 이미지 (로고·직인) ──────────────────────────────────────────────
def save_upload(data_url):
    raw = base64.b64decode(data_url.split(",", 1)[-1])
    if len(raw) > 15 * 1024 * 1024:
        raise ValueError("이미지가 너무 큽니다 (15MB 이하)")
    im = Image.open(io.BytesIO(raw))
    im.load()
    im = render.ImageOps.exif_transpose(im)
    if max(im.size) > 2400:
        im.thumbnail((2400, 2400))
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if render.has_alpha(im) else "RGB")
    b = io.BytesIO()
    im.save(b, "PNG")
    uid = hashlib.sha1(b.getvalue()).hexdigest()[:16]
    with open(ws("uploads", uid + ".png"), "wb") as f:
        f.write(b.getvalue())
    return uid


def load_upload(uid):
    if not uid or not re.fullmatch(r"[0-9a-f]{16}", uid):
        return None
    p = os.path.join(WS, "uploads", uid + ".png")
    if not os.path.exists(p):
        return None
    im = Image.open(p)
    im.load()
    return im


# ── 렌더·발급 ───────────────────────────────────────────────────────────
def draw(cfg, dpi=DPI):
    logo = load_upload(cfg.get("logo_id")) if (cfg.get("logo_mode") or "top") != "none" else None
    seal = load_upload(cfg.get("seal_id")) if cfg.get("seal_mode") == "upload" else None
    return render.render(cfg, dpi, logo=logo, seal=seal)


THUMBS = {}
SAMPLE = {"kind": "상장", "number": "2026-001", "name": "홍길동", "dept": "○○연구실", "position": "선임연구원",
          "text": phrases.phrases_for("상장")[0][1], "org": "○○연구원", "giver_title": "원장", "giver_name": "○○○"}


def thumb_jpeg(design):
    """디자인 선택 버튼용 작은 견본 (한 번 그려 메모리에 둠)"""
    if design not in THUMBS:
        b = io.BytesIO()
        render.render(dict(SAMPLE, design=design, date=datetime.date.today().isoformat()), 30).save(b, "JPEG", quality=85)
        THUMBS[design] = b.getvalue()
    return THUMBS[design]


def preview_jpeg(cfg):
    b = io.BytesIO()
    draw(cfg, PREVIEW_DPI).save(b, "JPEG", quality=88)
    return b.getvalue()


def cfg_for_row(cfg, row, number):
    c = dict(cfg, number=number, name=row.get("name", ""), dept=row.get("dept", ""), position=row.get("position", ""))
    if (row.get("text") or "").strip():
        c["text"] = row["text"].strip()
    return c


def _record(c, rid, page=1):
    return {"id": rid, "page": page, "ts": datetime.datetime.now().isoformat(timespec="seconds"), "date": c.get("date") or "",
            "number": render.number_label(c.get("number")), "name": c.get("name") or "", "dept": c.get("dept") or "",
            "position": c.get("position") or "", "kind": c.get("kind") or "", "award": c.get("award") or "",
            "org": c.get("org") or "", "design": c.get("design") or ""}


def safe_name(s):
    return re.sub(r'[\\/:*?"<>|\s]+', "_", (s or "").strip()) or "상장"


def issue(cfg, rows=None, fmt="pdf"):
    """발급 → (bytes, 파일명, content-type). rows 가 있으면 일괄(번호 자동 증가). 발급본 PDF 는 WORKSPACE/issued 에 보관."""
    rid = f"{datetime.date.today()}-{secrets.token_hex(3)}"
    if rows:
        rows = rows[:MAX_BATCH]
        start = (cfg.get("number") or "").strip() or next_number()
        cfgs = [cfg_for_row(cfg, r, bump(start, i)) for i, r in enumerate(rows)]
    else:
        cfgs = [cfg]
    imgs = [draw(c) for c in cfgs]
    pdf = render.pdf_bytes(imgs, DPI)
    with open(ws("issued", rid + ".pdf"), "wb") as f:
        f.write(pdf)
    log_issue([_record(c, rid, i + 1) for i, c in enumerate(cfgs)])
    kind = safe_name(cfg.get("kind"))
    base = f"{kind}_{safe_name(cfgs[0].get('name'))}" if len(cfgs) == 1 else f"{kind}_일괄{len(cfgs)}장"
    if fmt == "png" and len(cfgs) == 1:
        return render.png_bytes(imgs[0], DPI), base + ".png", "image/png"
    if fmt in ("zip-pdf", "zip-png"):
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
            for i, (c, im) in enumerate(zip(cfgs, imgs)):
                stem = f"{i + 1:03d}_{safe_name(c.get('number'))}_{safe_name(c.get('name'))}"
                if fmt == "zip-png":
                    z.writestr(stem + ".png", render.png_bytes(im, DPI))
                else:
                    z.writestr(stem + ".pdf", render.pdf_bytes([im], DPI))
        return b.getvalue(), base + ".zip", "application/zip"
    return pdf, base + ".pdf", "application/pdf"


# ── 수상자 목록 (CSV·엑셀 붙여넣기·xlsx) ─────────────────────────────────
HEADER = {"이름": "name", "성명": "name", "name": "name", "소속": "dept", "부서": "dept", "dept": "dept",
          "직위": "position", "직급": "position", "position": "position", "문구": "text", "공적": "text", "text": "text"}


def parse_rows(text):
    """'이름,소속,직위[,문구]' — 탭(엑셀 붙여넣기)·쉼표 모두. 첫 줄이 머리글이면 그 순서를 따른다."""
    text = (text or "").strip("﻿ \n")
    if not text:
        return []
    lines = text.splitlines()
    delim = "\t" if any("\t" in l for l in lines[:5]) else ","
    data = [r for r in csv.reader(lines, delimiter=delim) if any(x.strip() for x in r)]
    cols = ["name", "dept", "position", "text"]
    if data and data[0] and data[0][0].strip().lower() in HEADER:
        cols = [HEADER.get(h.strip().lower(), "") for h in data[0]]
        data = data[1:]
    out = []
    for r in data:
        row = {k: "" for k in ("name", "dept", "position", "text")}
        for k, v in zip(cols, r):
            if k:
                row[k] = v.strip()
        if len(r) > len(cols) and cols[-1] == "text":  # 문구에 쉼표가 있어 칸이 더 나뉜 경우
            row["text"] = delim.join(x.strip() for x in r[len(cols) - 1:])
        if row["name"]:
            out.append(row)
    return out


def xlsx_to_tsv(raw):
    """첫 시트를 TSV 로 (표준 라이브러리만). 숫자·문자 셀만."""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns):
                shared.append("".join(t.text or "" for t in si.iter("{%s}t" % ns["m"])))
        sheets = sorted(n for n in z.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))
        if not sheets:
            raise ValueError("시트가 없습니다")
        root = ET.fromstring(z.read(sheets[0]))
    lines = []
    for row in root.iter("{%s}row" % ns["m"]):
        cells = {}
        for c in row.findall("m:c", ns):
            col = re.match(r"[A-Z]+", c.get("r", "A")).group()
            idx = 0
            for ch in col:
                idx = idx * 26 + ord(ch) - 64
            v = c.find("m:v", ns)
            t = c.get("t")
            if t == "s" and v is not None:
                val = shared[int(v.text)]
            elif t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter("{%s}t" % ns["m"]))
            else:
                val = v.text if v is not None else ""
            cells[idx - 1] = (val or "").replace("\t", " ").replace("\n", " ")
        if cells:
            lines.append("\t".join(cells.get(i, "") for i in range(max(cells) + 1)))
    return "\n".join(lines)


# ── LLM (선택: 문구 다듬기) ───────────────────────────────────────────────
POLISH = """너는 한국 공공기관의 상장·표창장·감사장 문안을 다듬는 전문가다.
사용자가 쓴 수상 사유를 격식 있는 상장 문체 한 단락으로 고쳐 쓴다.
- 상장·표창장·공로상·우수상: "위 사람은 …하였으므로 이에 (상훈 종류)을/를 수여합니다." 꼴. 표창장은 "…하였으므로 이에 표창합니다."
- 감사장: "귀하는 …하셨기에 깊은 감사의 마음을 담아 이 감사장을 드립니다." 꼴
- 사실(업적·숫자·행사명)은 바꾸거나 지어내지 않는다. 숫자는 그대로 쓴다(예: "논문 3편" → "논문 3편", "다수의"로 바꾸지 않음). 2~3문장 이내, 120자 안팎. 과장된 미사여구는 피한다.
- 출력은 다듬은 문구 한 단락만. 따옴표·설명·머리말 없이."""


def chat(system, user, model=None):
    model = model or MODEL
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        if LLM_API == "openai":
            hdr = {"Content-Type": "application/json", **({"Authorization": f"Bearer {LLM_KEY}"} if LLM_KEY else {})}
            req = urllib.request.Request(LLM_BASE + "/chat/completions",
                                         json.dumps({"model": model, "temperature": 0.3, "messages": msgs}).encode(), hdr)
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.load(r)["choices"][0]["message"]["content"]
        body = {"model": model, "stream": False, "think": False, "options": {"temperature": 0.3}, "messages": msgs}
        for attempt in (0, 1):
            try:
                req = urllib.request.Request(LLM_BASE + "/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=300) as r:
                    return json.load(r)["message"]["content"]
            except urllib.error.HTTPError as e:
                msg = e.read().decode(errors="replace")
                if attempt == 0 and "think" in msg:
                    body.pop("think")
                    continue
                raise RuntimeError(f"LLM HTTP {e.code}: {msg[:200]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"LLM 서버 연결 실패 ({LLM_BASE}): {e.reason}")


def polish(text, kind, model=None):
    out = chat(POLISH, f"[상훈 종류] {kind or '상장'}\n[수상 사유 초안]\n{text}", model)
    out = re.sub(r"<think>.*?</think>", "", out, flags=re.S).strip().strip('"“”')
    return re.sub(r"\s*\n\s*", " ", out)


def models():
    try:
        if LLM_API == "openai":
            req = urllib.request.Request(LLM_BASE + "/models", headers={"Authorization": f"Bearer {LLM_KEY}"} if LLM_KEY else {})
            with urllib.request.urlopen(req, timeout=3) as r:
                return [m["id"] for m in json.load(r)["data"]]
        with urllib.request.urlopen(LLM_BASE + "/api/tags", timeout=3) as r:
            return [m["name"] for m in json.load(r)["models"]]
    except Exception:
        return []


def meta():
    return {"designs": [{"id": k, "name": v["name"]} for k, v in render.DESIGNS.items()],
            "kinds": phrases.KINDS, "phrases": {k: phrases.phrases_for(k) for k in phrases.KINDS},
            "next_number": next_number(), "today": datetime.date.today().isoformat(), "model": MODEL}


# ── HTTP ───────────────────────────────────────────────────────────────
HTML = read(os.path.join(ROOT, "ui.html")) if os.path.exists(os.path.join(ROOT, "ui.html")) else "ui.html 없음"

# ── 저작권 표기 (LICENSE·NOTICE 참고) ─────────────────────────────────────
_SIG = __import__("base64").b64decode("wqkgMjAyNiBnZ2dnODY1NyDCtyBkb25nanVraW0uZGV2QGdtYWlsLmNvbQ==").decode()
_SIG_A = __import__("base64").b64decode("Z2dnZzg2NTcgPGRvbmdqdWtpbS5kZXZAZ21haWwuY29tPg==").decode()


def signed(html):
    """화면에 저작권 표기를 붙인다. ui.html 에서 지워져도 서버가 내보낼 때 다시 붙는다."""
    name, mail = _SIG.split(" · ")
    if 'name="author"' not in html:
        meta = f'<meta name="author" content="{name[7:]} <{mail}>">'
        html = html.replace("<head>", "<head>" + meta, 1) if "<head>" in html else meta + html
    if "data-sig" not in html:
        tag = (f'<!-- {_SIG} --><div data-sig title="{mail}" style="text-align:center;font-size:11px;color:#9aa0a6;'
               f'opacity:.55;margin:28px 0 8px">{name}</div>')
        html = html.replace("</body>", tag + "</body>", 1) if "</body>" in html else html + tag
    return html


class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        if "/api/issue" in (a[0] if a else "") or "/api/polish" in (a[0] if a else ""):
            super().log_message(fmt, *a)

    def _send(self, body, ctype="application/json", code=200, filename=None):
        b = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("X-Author", _SIG_A)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        if filename:
            self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + urllib.parse.quote(filename))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        path = self.path.split("?")[0]
        try:
            if path == "/api/health":
                return self._send({"ok": True})
            if path == "/api/meta":
                return self._send(meta())
            if path == "/api/models":
                return self._send(models())
            if path == "/api/history":
                return self._send(history(500))
            m = re.fullmatch(r"/api/issued/(\d{4}-\d{2}-\d{2}-[0-9a-f]{6})\.pdf", path)
            if m:
                with open(os.path.join(WS, "issued", m.group(1) + ".pdf"), "rb") as f:
                    return self._send(f.read(), "application/pdf")
            m = re.fullmatch(r"/api/thumb/(\w+)\.jpg", path)
            if m and m.group(1) in render.DESIGNS:
                return self._send(thumb_jpeg(m.group(1)), "image/jpeg")
            m = re.fullmatch(r"/api/upload/([0-9a-f]{16})", path)
            if m:
                with open(os.path.join(WS, "uploads", m.group(1) + ".png"), "rb") as f:
                    return self._send(f.read(), "image/png")
            self._send(signed(HTML).encode(), "text/html; charset=utf-8")
        except FileNotFoundError:
            self._send({"error": "없음"}, code=404)
        except Exception as e:
            self._send({"error": f"{type(e).__name__}: {e}"}, code=500)

    def do_POST(self):
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            cfg = req.get("cfg") or {}
            if self.path == "/api/preview":
                return self._send(preview_jpeg(cfg), "image/jpeg")
            if self.path == "/api/issue":
                rows = req.get("rows") or None
                body, name, ctype = issue(cfg, rows, req.get("format") or "pdf")
                return self._send(body, ctype, filename=name)
            if self.path == "/api/upload":
                return self._send({"id": save_upload(req.get("data") or "")})
            if self.path == "/api/rows":
                text = req.get("text") or ""
                if req.get("xlsx"):
                    text = xlsx_to_tsv(base64.b64decode(req["xlsx"].split(",", 1)[-1]))
                return self._send({"rows": parse_rows(text)})
            if self.path == "/api/polish":
                if not (req.get("text") or "").strip():
                    return self._send({"error": "다듬을 문구가 비어 있습니다"}, code=400)
                return self._send({"text": polish(req["text"], req.get("kind"), req.get("model"))})
            self._send({"error": "없는 경로"}, code=404)
        except Exception as e:
            self._send({"error": f"{type(e).__name__}: {e}"}, code=500)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        cfg = json.load(open(sys.argv[2], encoding="utf-8"))
        out = sys.argv[3] if len(sys.argv) > 3 else "award.pdf"
        img = draw(cfg)
        with open(out, "wb") as f:
            f.write(render.png_bytes(img) if out.lower().endswith(".png") else render.pdf_bytes([img]))
        print(out)
        sys.exit(0)
    print(f"award local → http://localhost:{PORT}  (llm={LLM_API} {LLM_BASE} {MODEL}, workspace={WS})  {_SIG}")
    ThreadingHTTPServer(("", PORT), H).serve_forever()
