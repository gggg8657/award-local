#!/usr/bin/env python3
"""LLM 없이 검증: 디자인 7종×세로/가로 렌더 → 직인 자동 생성 → 로고(합성 이미지) → PDF/PNG(300dpi) → 일괄 발급(PDF·ZIP)
→ 번호 자동 증가·이력 → CSV/엑셀 붙여넣기/xlsx 파싱 → 문구 5개 이상·조사 → 다듬기(가짜 LLM) → HTTP → ui.html 로컬 자산만.
WORKSPACE 는 임시 폴더로 바꿔 실데이터 폴더에 흔적을 남기지 않는다.
python3 selftest.py            # SELFTEST_OUT=폴더 를 주면 렌더 결과 PNG 를 거기 저장(눈으로 확인용)"""
import io, json, os, re, shutil, sys, tempfile, threading, urllib.request, zipfile

TMP = tempfile.mkdtemp(prefix="award-selftest-")
os.environ["WORKSPACE"] = TMP
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app, phrases, render  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

OUT = os.environ.get("SELFTEST_OUT")
try:
    assert app.WS == TMP, "WORKSPACE 가 임시 폴더가 아님"
    BASE = dict(kind="상장", award="2026년도 연구성과 우수상", number="2026-001", name="홍길동", dept="인공지능응용연구실",
                position="선임연구원", text=phrases.phrases_for("상장")[0][1], date="2026-10-06", org="한국원자력연구원",
                giver_title="원장", giver_name="김철수", seal_mode="auto-square")

    # 1) 디자인 5종 × 세로/가로 — 300dpi A4 크기, 디자인마다 다른 그림
    assert len(render.DESIGNS) >= 5
    sigs = set()
    for d in render.DESIGNS:
        for orient, size in (("portrait", (2480, 3508)), ("landscape", (3508, 2480))):
            im = render.render(dict(BASE, design=d, orient=orient), 300)
            assert im.size == size, (d, orient, im.size)
            ext = im.convert("L").getextrema()
            assert ext[0] < 80 and ext[1] > 200, f"{d}: 글자·바탕이 안 보임 {ext}"
            if orient == "portrait":
                sigs.add(im.resize((40, 56)).tobytes())
            if OUT:
                os.makedirs(OUT, exist_ok=True)
                im.save(os.path.join(OUT, f"{d}-{orient}.png"), dpi=(300, 300))
    assert len(sigs) == len(render.DESIGNS), "디자인끼리 그림이 같음"
    assert len(render.DESIGNS) >= 7 and {"goldframe", "goldcorner"} <= set(render.DESIGNS)

    # 1-1) 흰 바탕 금테·모서리 금띠: 흰 바탕, 금색에 광택(여러 톤), 2모서리 옵션, 금띠가 글자·직인 자리를 침범하지 않음
    def px_mm(im, x, y, dpi=50):
        return im.getpixel((int(x * dpi / 25.4), int(y * dpi / 25.4)))
    for orient in ("portrait", "landscape"):
        W, H = (210, 297) if orient == "portrait" else (297, 210)
        gf = render.render(dict(BASE, design="goldframe", orient=orient), 50)
        assert px_mm(gf, 4, 4) == (255, 255, 255), "흰 바탕이 아님"
        tones = {px_mm(gf, x, 10.5) for x in range(12, int(W) - 12, 3)}
        assert len(tones) > 8 and all(r > b + 30 for r, g, b in tones), f"금 광택 톤 부족 {len(tones)}"
        g4 = render.render(dict(BASE, design="goldcorner", orient=orient), 50)
        g2 = render.render(dict(BASE, design="goldcorner", orient=orient, corners="2"), 50)
        for im, corners in ((g4, ("tl", "tr", "bl", "br")), (g2, ("tl", "br"))):
            for cn in ("tl", "tr", "bl", "br"):
                x = 2 if cn in ("tl", "bl") else W - 2
                y = 27 if cn in ("tl", "tr") else H - 27  # x+y≈29mm → 굵은 띠 안
                r, g, b = px_mm(im, x, y)
                assert (r > b + 30) == (cn in corners), (orient, cn, (r, g, b))
        blank = render.render(dict(design="goldcorner", orient=orient, kind="", number="", seal_mode="none", date="x", text=""), 50)
        full = render.render(dict(BASE, design="goldcorner", orient=orient, kind="표창장", award="아주 긴 상훈명 " * 3), 50)
        from PIL import ImageChops
        diff = ImageChops.difference(blank, full).convert("L").point(lambda v: 255 if v > 40 else 0)
        k = 50 / 25.4
        bb = diff.getbbox()
        for cx, cy in ((0, 0), (W, 0), (0, H), (W, H)):  # 글자·직인 영역 상자의 네 꼭짓점이 금띠(모서리에서 45mm) 밖
            nx = bb[0] / k if cx == 0 else W - bb[2] / k
            ny = bb[1] / k if cy == 0 else H - bb[3] / k
            assert nx + ny > 46, (orient, cx, cy, nx + ny)

    # 2) 직인: 자동 사각/원형은 빨간 픽셀, 없음은 없음
    def red(im):
        b = im.convert("RGB").resize((im.width // 4, im.height // 4)).tobytes()
        return sum(1 for i in range(0, len(b), 3) if b[i] > 150 and b[i + 1] < 90 and b[i + 2] < 90)
    sq = render.render(dict(BASE, design="official"), 100)
    rd = render.render(dict(BASE, design="official", seal_mode="auto-round"), 100)
    no = render.render(dict(BASE, design="official", seal_mode="none"), 100)
    assert red(sq) > 20 and red(rd) > 20 and red(no) == 0, (red(sq), red(rd), red(no))
    assert render.seal_text_auto("한국원자력연구원", "원장") == "한국원자력연구원장인"
    assert render.seal_text_auto("○○센터", "센터장") == "○○센터장인"
    s = render.make_seal("가나다라마바사아자차", "square", 300)
    assert s.size == (300, 300) and s.getchannel("A").getextrema()[1] > 150

    # 3) 업로드: 합성 로고(실존 기관 아님)·흰 바탕 직인 → 저장·렌더
    logo = Image.new("RGB", (400, 200), "white")
    ImageDraw.Draw(logo).ellipse([20, 20, 180, 180], fill=(0, 90, 160))
    b = io.BytesIO(); logo.save(b, "PNG")
    lid = app.save_upload("data:image/png;base64," + __import__("base64").b64encode(b.getvalue()).decode())
    assert re.fullmatch(r"[0-9a-f]{16}", lid) and app.load_upload(lid).size == (400, 200)
    seal = Image.new("RGB", (200, 200), "white")
    ImageDraw.Draw(seal).rectangle([10, 10, 190, 190], outline=(200, 0, 0), width=12)
    b = io.BytesIO(); seal.save(b, "JPEG")
    sid = app.save_upload("data:image/jpeg;base64," + __import__("base64").b64encode(b.getvalue()).decode())
    up = render.prepare_upload_seal(app.load_upload(sid))
    assert up.mode == "RGBA" and up.getpixel((100, 100))[3] < 20 and up.getpixel((15, 100))[3] > 200, "흰 바탕이 투명해지지 않음"
    for mode in ("top", "watermark"):
        for d in ("traditional", "ribbon"):
            im = app.draw(dict(BASE, design=d, logo_id=lid, logo_mode=mode, seal_mode="upload", seal_id=sid), 100)
            if OUT:
                im.save(os.path.join(OUT, f"logo-{d}-{mode}.png"))
    assert app.load_upload("../../etc/passwd") is None

    # 4) 한 장 발급: PDF·PNG(300dpi) + 이력
    pdf, name, ctype = app.issue(dict(BASE, design="hanji"), fmt="pdf")
    assert pdf[:5] == b"%PDF-" and ctype == "application/pdf" and name == "상장_홍길동.pdf"
    assert len(re.findall(rb"/Type\s*/Page\b", pdf)) == 1
    png, name, ctype = app.issue(dict(BASE, number="2026-002"), fmt="png")
    im = Image.open(io.BytesIO(png))
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and im.size == (2480, 3508) and round(im.info["dpi"][0]) == 300, im.info
    h = app.history()
    assert [x["number"] for x in h[:2]] == ["제 2026-002 호", "제 2026-001 호"] and h[0]["name"] == "홍길동"
    assert os.path.exists(os.path.join(TMP, "issued", h[0]["id"] + ".pdf"))

    # 5) 번호 증가
    assert app.bump("2026-009") == "2026-010" and app.bump("제 7 호", 3) == "제 10 호" and app.bump("KAERI-2026-099", 1) == "KAERI-2026-100"
    assert app.bump("번호없음") == "번호없음"
    assert app.next_number(2026) == "2026-003"

    # 6) 수상자 목록: 엑셀 붙여넣기(탭) / CSV(머리글·따옴표 속 쉼표) / xlsx
    r = app.parse_rows("홍길동\t인공지능응용연구실\t선임연구원\n김영희\t원자력안전연구소\t책임연구원\t위 사람은 특별히 …하였으므로 이에 상장을 수여합니다.\n\n")
    assert [x["name"] for x in r] == ["홍길동", "김영희"] and r[1]["text"].startswith("위 사람은") and r[0]["text"] == ""
    r = app.parse_rows('성명,직위,소속\n이철수,연구원,"가속기, 빔 이용 연구부"\n')
    assert r == [{"name": "이철수", "dept": "가속기, 빔 이용 연구부", "position": "연구원", "text": ""}], r
    xb = io.BytesIO()
    with zipfile.ZipFile(xb, "w") as z:
        z.writestr("xl/sharedStrings.xml", '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>이름</t></si><si><t>소속</t></si><si><t>박민수</t></si><si><t>디지털혁신부</t></si></sst>')
        z.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                   '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
                   '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2" t="s"><v>3</v></c><c r="C2" t="inlineStr"><is><t>책임</t></is></c></row></sheetData></worksheet>')
    assert app.parse_rows(app.xlsx_to_tsv(xb.getvalue())) == [{"name": "박민수", "dept": "디지털혁신부", "position": "", "text": ""}]

    # 7) 일괄 발급: 3명 → PDF 3쪽, ZIP(PDF/PNG) 3개, 번호 2026-009 부터
    rows = app.parse_rows("가나다\tA실\t연구원\n라마바\tB실\t선임\n사아자\tC실\t책임\t개별 문구입니다.")
    pdf, name, _ = app.issue(dict(BASE, number="2026-009"), rows, "pdf")
    assert len(re.findall(rb"/Type\s*/Page\b", pdf)) == 3 and name == "상장_일괄3장.pdf"
    h = app.history()
    assert [x["number"] for x in h[:3]] == ["제 2026-011 호", "제 2026-010 호", "제 2026-009 호"], [x["number"] for x in h[:3]]
    assert [x["page"] for x in h[:3]] == [3, 2, 1] and h[0]["name"] == "사아자"
    for fmt, ext in (("zip-pdf", ".pdf"), ("zip-png", ".png")):
        z, name, ctype = app.issue(dict(BASE, number="2026-020"), rows, fmt)
        names = zipfile.ZipFile(io.BytesIO(z)).namelist()
        assert ctype == "application/zip" and len(names) == 3 and all(n.endswith(ext) for n in names), names
        assert names[0].startswith("001_2026-020_가나다"), names
    assert app.next_number(2026) == "2026-023"
    c = app.cfg_for_row(BASE, rows[2], "x")
    assert c["text"] == "개별 문구입니다." and app.cfg_for_row(BASE, rows[0], "x")["text"] == BASE["text"]

    # 8) 문구: 종류별 5개 이상, 격식 꼴, 조사
    for k in phrases.KINDS:
        ps = phrases.phrases_for(k)
        assert len(ps) >= 5 and all(t.endswith("니다.") and "{" not in t for _, t in ps), k
    assert phrases.josa("상장") == "상장을" and phrases.josa("트로피") == "트로피를" and phrases.josa("최우수상") == "최우수상을"
    assert "최우수상을 수여합니다" in phrases.phrases_for("최우수상")[0][1]

    # 9) 다듬기 (가짜 LLM)
    seen = []
    app.chat = lambda system, user, model=None: (seen.append(user), "<think>x</think>\n“위 사람은 성실히 근무하였으므로\n이에 상장을 수여합니다.”")[1]
    assert app.polish("열심히 일함", "상장") == "위 사람은 성실히 근무하였으므로 이에 상장을 수여합니다." and "[상훈 종류] 상장" in seen[0]

    # 10) HTTP: 화면·메타·미리보기·이력
    srv = app.ThreadingHTTPServer(("127.0.0.1", 0), app.H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/"
    html = urllib.request.urlopen(base).read().decode()
    assert "상장 생성기" in html and "data-sig" in html
    meta = json.load(urllib.request.urlopen(base + "api/meta"))
    assert len(meta["designs"]) >= 5 and meta["next_number"] == app.next_number() and len(meta["phrases"]["감사장"]) >= 5
    req = urllib.request.Request(base + "api/preview", json.dumps({"cfg": dict(BASE, design="ribbon", orient="landscape")}).encode(), {"Content-Type": "application/json"})
    jpg = urllib.request.urlopen(req).read()
    assert jpg[:2] == b"\xff\xd8" and Image.open(io.BytesIO(jpg)).size[0] > Image.open(io.BytesIO(jpg)).size[1]
    for d in render.DESIGNS:
        assert urllib.request.urlopen(base + f"api/thumb/{d}.jpg").read()[:2] == b"\xff\xd8"
    assert len(json.load(urllib.request.urlopen(base + "api/history"))) == 2 + 3 + 6
    srv.shutdown()

    # 11) 폐쇄망: 외부 CDN 없음, 폰트 동봉, 저작권 표기
    ui = app.read(os.path.join(app.ROOT, "ui.html"))
    assert not re.search(r'<(script|link|img)[^>]+(src|href)="https?://', ui), "외부 CDN 참조 있음"
    for f in ("NanumMyeongjo-Regular", "NanumMyeongjo-Bold", "NanumMyeongjo-ExtraBold", "NanumGothic-Regular", "NanumGothic-Bold", "NanumGothic-ExtraBold"):
        assert os.path.exists(os.path.join(render.FONTS, f + ".ttf")), f
    assert os.path.exists(os.path.join(render.FONTS, "OFL.txt"))
    _src = open(os.path.join(app.ROOT, "app.py"), encoding="utf-8").read()
    assert "wqkgMjAyNiBnZ2dnODY1NyDCtyBkb25nanVraW0uZGV2QGdtYWlsLmNvbQ==" in _src and "signed(" in _src and "X-Author" in _src, "저작권 표기 누락"
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print("selftest OK")
