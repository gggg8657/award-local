"""상장 렌더러 — Pillow 로 A4 한 장을 그린다. 좌표는 mm 로 쓰고 dpi 로 환산. 미리보기·PNG·PDF 가 같은 그림.

  render(cfg, dpi=300) -> PIL.Image (RGB)
  pdf_bytes([img, ...]) / png_bytes(img)
"""
import datetime
import functools
import io
import math
import os
import random
import re

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(ROOT, "static", "fonts")
MJ, MJB, MJX = "NanumMyeongjo-Regular", "NanumMyeongjo-Bold", "NanumMyeongjo-ExtraBold"
GT, GTB, GTX = "NanumGothic-Regular", "NanumGothic-Bold", "NanumGothic-ExtraBold"

# 디자인 5종 — 색은 (R,G,B). pad: 테두리 안쪽 본문 여백(mm). 그림 요소는 전부 코드로 그린다(이미지 파일 없음).
DESIGNS = {
    "traditional": {"name": "전통 금색 테두리", "paper": (252, 248, 236), "ink": (28, 24, 20), "title": (24, 18, 12),
                    "accent": (178, 140, 56), "dark": (122, 90, 28), "pad": 31, "tfont": MJX, "font": MJ, "bold": MJB},
    "official": {"name": "청색 공문형", "paper": (255, 255, 255), "ink": (22, 24, 32), "title": (20, 48, 112),
                 "accent": (20, 48, 112), "dark": (12, 30, 76), "pad": 24, "tfont": MJX, "font": MJ, "bold": MJB},
    "modern": {"name": "모던 미니멀", "paper": (255, 255, 255), "ink": (38, 40, 46), "title": (24, 26, 32),
               "accent": (0, 112, 140), "dark": (0, 76, 96), "pad": 24, "tfont": GTX, "font": GT, "bold": GTB},
    "hanji": {"name": "한지 질감", "paper": (242, 232, 210), "ink": (40, 30, 22), "title": (58, 30, 20),
              "accent": (138, 42, 36), "dark": (96, 30, 24), "pad": 26, "tfont": MJX, "font": MJ, "bold": MJB},
    "ribbon": {"name": "리본·메달형", "paper": (255, 252, 245), "ink": (30, 26, 24), "title": (100, 22, 34),
               "accent": (190, 148, 60), "dark": (128, 92, 28), "ribbon": (150, 26, 42), "pad": 24, "tfont": MJX, "font": MJ, "bold": MJB},
    "goldframe": {"name": "흰 바탕 금테", "paper": (255, 255, 255), "ink": (30, 27, 22), "title": (34, 28, 18),
                  "accent": (176, 136, 54), "dark": (118, 86, 26), "pad": 27, "tfont": MJX, "font": MJ, "bold": MJB},
    "goldcorner": {"name": "모서리 금띠", "paper": (255, 255, 255), "ink": (30, 27, 22), "title": (34, 28, 18),
                   "accent": (176, 136, 54), "dark": (118, 86, 26), "pad": 26, "tfont": MJX, "font": MJ, "bold": MJB},
}
CAPTION = {"상장": "CERTIFICATE OF AWARD", "표창장": "CERTIFICATE OF COMMENDATION", "감사장": "CERTIFICATE OF APPRECIATION",
           "공로상": "MERIT AWARD", "우수상": "EXCELLENCE AWARD"}


@functools.lru_cache(maxsize=256)
def font(name, px):
    return ImageFont.truetype(os.path.join(FONTS, name + ".ttf"), max(4, int(px)))


def kdate(s):
    """'2026-10-06' → '2026년 10월 6일' (이미 한국식이면 그대로)"""
    try:
        d = datetime.date.fromisoformat((s or "").strip())
    except ValueError:
        return (s or "").strip() or kdate(datetime.date.today().isoformat())
    return f"{d.year}년 {d.month}월 {d.day}일"


def number_label(n):
    n = str(n if n is not None else "").strip()
    if not n or n.startswith("제"):
        return n
    return f"제 {n} 호"


def spaced_name(s):
    """두·세 글자 한글 이름은 상장 관례대로 띄어 쓴다: 홍길동 → 홍 길 동"""
    s = (s or "").strip()
    return " ".join(s) if re.fullmatch(r"[가-힣]{2,3}", s) else s


def seal_text_auto(org, giver_title):
    org = (org or "").strip() or "기관"
    return org + ("장" if (giver_title or "").strip().endswith("장") and not org.endswith("장") else "") + "인"


# ── 그리기 도우미 ─────────────────────────────────────────────────────────
class Canvas:
    def __init__(self, img, dpi, design):
        self.img, self.k, self.d = img, dpi / 25.4, design
        self.draw = ImageDraw.Draw(img)

    def px(self, mm):
        return int(round(mm * self.k))

    def f(self, name, mm):
        return font(name, mm * self.k)

    def w(self, s, fnt, gap=0):
        """글자 사이 gap(px) 을 둔 폭(px)"""
        if not s:
            return 0
        return (fnt.getlength(s) if not gap else sum(fnt.getlength(c) for c in s) + gap * (len(s) - 1))

    def text(self, x, y, s, fnt, fill, anchor="ls", gap=0):
        """x,y 는 px. gap>0 이면 한 글자씩. anchor 는 l/m/r + s(baseline)"""
        if not gap:
            self.draw.text((x, y), s, font=fnt, fill=fill, anchor=anchor)
            return
        tw = self.w(s, fnt, gap)
        x0 = x - tw / 2 if anchor[0] == "m" else x - tw if anchor[0] == "r" else x
        for c in s:
            self.draw.text((x0, y), c, font=fnt, fill=fill, anchor="l" + anchor[1])
            x0 += fnt.getlength(c) + gap

    def rect(self, inset, width_mm, color, W, H):
        i, w = self.px(inset), max(1, self.px(width_mm))
        self.draw.rectangle([i, i, self.px(W) - i - 1, self.px(H) - i - 1], outline=color, width=w)


def _alpha_paste(base, im, xy, opacity=1.0):
    im = im.convert("RGBA")
    if opacity < 1:
        im.putalpha(im.getchannel("A").point(lambda v: int(v * opacity)))
    base.paste(im, xy, im)


def _multiply_paste(base, im, xy):
    """흰 바탕 이미지(JPG 로고 등)는 곱하기로 얹어 종이 색이 비치게"""
    x, y = xy
    box = (x, y, x + im.width, y + im.height)
    region = base.crop(box)
    base.paste(ImageChops.multiply(region, im.convert("RGB")), box)


def has_alpha(im):
    return im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)


def paste_image(base, im, xy, opacity=1.0):
    if has_alpha(im):
        _alpha_paste(base, im, xy, opacity)
    elif opacity < 1:
        paper = Image.new("RGB", im.size, (255, 255, 255))
        _multiply_paste(base, Image.blend(paper, im.convert("RGB"), opacity), xy)
    else:
        _multiply_paste(base, im, xy)


def fit(im, max_w, max_h):
    r = min(max_w / im.width, max_h / im.height)
    return im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))), Image.LANCZOS)


# ── 직인 ────────────────────────────────────────────────────────────────
def _glyph(ch, fnt_name, cw, chh, color):
    """한 글자를 칸(cw×chh px)에 꽉 차게 늘려 그린 RGBA"""
    size = int(max(cw, chh) * 1.2) + 8
    m = Image.new("L", (size * 2, size * 2), 0)
    ImageDraw.Draw(m).text((size // 2, size // 2), ch, font=font(fnt_name, size), fill=255)
    bb = m.getbbox()
    if not bb:
        return Image.new("RGBA", (max(1, cw), max(1, chh)), (0, 0, 0, 0))
    m = m.crop(bb).resize((max(1, cw), max(1, chh)), Image.LANCZOS)
    g = Image.new("RGBA", m.size, color + (0,))
    g.putalpha(m)
    return g


def make_seal(text, shape, px, color=(196, 30, 36), seed=7):
    """기관명 글자로 빨간 도장. shape: square(사각, 세로쓰기 오른쪽→왼쪽) | round(원형, 둘레글자+가운데 '인')"""
    text = re.sub(r"\s+", "", text or "") or "인"
    s = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(s)
    bw = max(2, int(px * 0.06))
    if shape == "round":
        d.ellipse([bw // 2, bw // 2, px - bw // 2 - 1, px - bw // 2 - 1], outline=color, width=bw)
        ring = text[:-1] if len(text) > 1 and text.endswith("인") else text
        center = "인"
        n = max(1, len(ring))
        r_txt = px * 0.36
        ch = int(px * min(0.2, 2.2 / max(n, 6)))
        for i, c in enumerate(ring):
            a = -math.pi / 2 - math.pi * 0.78 + (2 * math.pi * 0.78) * (i + 0.5) / n if n > 1 else -math.pi / 2  # 위쪽 280° 호
            g = _glyph(c, MJX, ch, ch, color).rotate(-math.degrees(a + math.pi / 2), resample=Image.BICUBIC, expand=True)
            cx, cy = px / 2 + r_txt * math.cos(a), px / 2 + r_txt * math.sin(a)
            s.alpha_composite(g, (int(cx - g.width / 2), int(cy - g.height / 2)))
        ir = px * 0.22
        d.ellipse([px / 2 - ir, px / 2 - ir, px / 2 + ir, px / 2 + ir], outline=color, width=max(1, bw // 2))
        g = _glyph(center, MJX, int(ir * 1.25), int(ir * 1.25), color)
        s.alpha_composite(g, (int(px / 2 - g.width / 2), int(px / 2 - g.height / 2)))
    else:
        d.rounded_rectangle([bw // 2, bw // 2, px - bw // 2 - 1, px - bw // 2 - 1], radius=int(px * 0.04), outline=color, width=bw)
        n = len(text)
        cols = max(1, round(math.sqrt(n)))
        counts = [n // cols + (1 if i < n % cols else 0) for i in range(cols)]  # 오른쪽 열이 한 글자 더
        inner = px - bw * 2 - int(px * 0.08)
        off = (px - inner) // 2
        cw = inner // cols
        k = 0
        for col, take in enumerate(counts):  # 오른쪽 열부터 위→아래
            chh = inner // take
            x = off + inner - (col + 1) * cw
            for r in range(take):
                g = _glyph(text[k], MJX, int(cw * 0.9), int(chh * 0.9), color)
                s.alpha_composite(g, (x + (cw - g.width) // 2, off + r * chh + (chh - g.height) // 2))
                k += 1
    # 인주 질감: 군데군데 빠진 점 + 살짝 번짐
    rng = random.Random(seed)
    a = s.getchannel("A")
    holes = Image.new("L", s.size, 255)
    hd = ImageDraw.Draw(holes)
    for _ in range(int(px * px / 900)):
        x, y, r = rng.uniform(0, px), rng.uniform(0, px), rng.uniform(0.4, 1.6) * px / 300
        hd.ellipse([x - r, y - r, x + r, y + r], fill=rng.randint(0, 140))
    a = ImageChops.multiply(a, holes).filter(ImageFilter.GaussianBlur(px / 600))
    s.putalpha(a.point(lambda v: int(v * 0.9)))
    return s


def prepare_upload_seal(im):
    """업로드한 직인: 투명 배경이 없으면 흰색을 투명으로"""
    im = ImageOps.exif_transpose(im)
    if has_alpha(im):
        return im.convert("RGBA")
    rgb = im.convert("RGB")
    a = ImageOps.invert(rgb.convert("L")).point(lambda v: min(255, int(v * 1.6)))
    out = rgb.convert("RGBA")
    out.putalpha(a)
    return out


# ── 배경·테두리 ─────────────────────────────────────────────────────────
def _meander_band(length, thick, color, line):
    """뇌문(雷文) 띠 — length×thick px 가로 띠"""
    band = Image.new("RGBA", (length, thick), (0, 0, 0, 0))
    d = ImageDraw.Draw(band)
    n = max(1, round(length / thick))
    u = length / n
    lw = line
    for i in range(n):
        x0 = i * u
        P = lambda a, b: (x0 + a * u, b * thick)
        pts = [P(0.1, 0.9), P(0.1, 0.1), P(0.9, 0.1), P(0.9, 0.7), P(0.35, 0.7), P(0.35, 0.35), P(0.65, 0.35), P(0.65, 0.5)]
        d.line(pts, fill=color, width=lw, joint="curve")
        d.line([P(0.1, 0.9), P(1.1, 0.9)] if i < n - 1 else [P(0.1, 0.9), P(0.9, 0.9)], fill=color, width=lw)
    return band


def _corner_rosette(cv, cx, cy, r, color, dark):
    d = cv.draw
    d.rectangle([cx - r, cy - r, cx + r, cy + r], outline=dark, width=max(1, cv.px(0.4)))
    for i in range(8):
        a = i * math.pi / 4
        x, y = cx + r * 0.45 * math.cos(a), cy + r * 0.45 * math.sin(a)
        rr = r * 0.32
        d.ellipse([x - rr, y - rr, x + rr, y + rr], outline=color, width=max(1, cv.px(0.35)))
    rr = r * 0.22
    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=color)


def deco_traditional(cv, W, H):
    d, D = cv.draw, cv.d
    cv.rect(8, 1.6, D["accent"], W, H)
    cv.rect(10, 0.35, D["dark"], W, H)
    b0, b1 = 12.0, 20.0  # 뇌문 띠 안팎
    t = cv.px(b1 - b0)
    lw = max(1, cv.px(0.55))
    for horiz, length in ((True, W - 2 * b1), (False, H - 2 * b1)):
        band = _meander_band(cv.px(length), t, D["accent"] + (255,), lw)
        if horiz:
            cv.img.paste(band, (cv.px(b1), cv.px(b0)), band)
            fl = band.transpose(Image.ROTATE_180)
            cv.img.paste(fl, (cv.px(b1), cv.px(H - b1)), fl)
        else:
            r = band.transpose(Image.ROTATE_270)
            cv.img.paste(r, (cv.px(W - b1), cv.px(b1)), r)
            l = band.transpose(Image.ROTATE_90)
            cv.img.paste(l, (cv.px(b0), cv.px(b1)), l)
    cv.rect(b0, 0.35, D["dark"], W, H)
    cv.rect(b1, 0.35, D["dark"], W, H)
    cv.rect(b1 + 1.6, 0.9, D["accent"], W, H)
    r = cv.px((b1 - b0) / 2)
    for cx, cy in ((b0 + (b1 - b0) / 2, b0 + (b1 - b0) / 2), (W - b0 - (b1 - b0) / 2, b0 + (b1 - b0) / 2),
                   (b0 + (b1 - b0) / 2, H - b0 - (b1 - b0) / 2), (W - b0 - (b1 - b0) / 2, H - b0 - (b1 - b0) / 2)):
        d.rectangle([cv.px(cx) - r, cv.px(cy) - r, cv.px(cx) + r, cv.px(cy) + r], fill=D["paper"])
        _corner_rosette(cv, cv.px(cx), cv.px(cy), r, D["accent"], D["dark"])


def deco_official(cv, W, H):
    D, d = cv.d, cv.draw
    cv.rect(10, 1.4, D["accent"], W, H)
    cv.rect(12.6, 0.4, D["accent"], W, H)
    s = cv.px(5)
    for x, y, sx, sy in ((12.6, 12.6, 1, 1), (W - 12.6, 12.6, -1, 1), (12.6, H - 12.6, 1, -1), (W - 12.6, H - 12.6, -1, -1)):
        X, Y = cv.px(x), cv.px(y)
        d.rectangle([min(X, X + sx * s), min(Y, Y + sy * s), max(X, X + sx * s), max(Y, Y + sy * s)], fill=D["accent"])


def deco_modern(cv, W, H):
    D, d = cv.d, cv.draw
    d.rectangle([0, 0, cv.px(9), cv.px(H)], fill=D["accent"])
    d.rectangle([cv.px(9), 0, cv.px(10.2), cv.px(H)], fill=(170, 210, 220))
    cv.rect(14, 0.3, (190, 194, 200), W, H)
    # 오른쪽 아래 기하 장식
    X, Y = cv.px(W - 14), cv.px(H - 14)
    for i, (sz, col) in enumerate(((38, (214, 236, 240)), (24, (160, 206, 216)), (12, D["accent"]))):
        p = cv.px(sz)
        d.polygon([(X, Y), (X - p, Y), (X, Y - p)], fill=col)


def deco_hanji(cv, W, H):
    D, img = cv.d, cv.img
    w, h = img.size
    rng = random.Random(11)
    # 큰 얼룩 + 고운 결
    for scale, amp in ((max(8, w // 40), 9), (max(32, w // 4), 8)):
        n = Image.effect_noise((max(2, w // scale * 4), max(2, h // scale * 4)), 60).resize((w, h), Image.BICUBIC)
        n = n.filter(ImageFilter.GaussianBlur(w / (w // scale * 4) * 0.8))  # 덩어리 경계를 부드럽게
        n = n.point(lambda v, a=amp: max(0, min(255, 255 - a + (v - 128) * a // 64)))
        img.paste(ImageChops.multiply(img, Image.merge("RGB", (n, n, n))))
    # 닥나무 섬유
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(over)
    lw = max(1, cv.px(0.12))
    for i in range(int(W * H / 45)):
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        L = cv.px(rng.uniform(2, 11))
        a = rng.uniform(0, math.pi)
        bend = rng.uniform(-0.6, 0.6)
        pts = []
        for t in range(7):
            tt = t / 6
            aa = a + bend * tt
            pts.append((x + math.cos(aa) * L * tt, y + math.sin(aa) * L * tt))
        col = (178, 156, 120, rng.randint(40, 90)) if i % 3 else (255, 251, 240, rng.randint(80, 150))
        od.line(pts, fill=col, width=lw)
    img.paste(Image.alpha_composite(img.convert("RGBA"), over).convert("RGB"))
    # 테두리: 굵은 선 + 가는 선, 모서리 꺾쇠
    cv.rect(11, 1.1, D["accent"], W, H)
    cv.rect(13.2, 0.35, D["accent"], W, H)
    d, L, t = cv.draw, cv.px(14), max(1, cv.px(0.9))
    for x, y, sx, sy in ((16, 16, 1, 1), (W - 16, 16, -1, 1), (16, H - 16, 1, -1), (W - 16, H - 16, -1, -1)):
        X, Y = cv.px(x), cv.px(y)
        d.line([(X + sx * L, Y), (X, Y), (X, Y + sy * L)], fill=D["accent"], width=t)
        d.line([(X + sx * cv.px(2.2), Y + sy * cv.px(2.2)), (X + sx * cv.px(5), Y + sy * cv.px(2.2))], fill=D["accent"], width=t)
        d.line([(X + sx * cv.px(2.2), Y + sy * cv.px(2.2)), (X + sx * cv.px(2.2), Y + sy * cv.px(5))], fill=D["accent"], width=t)


def deco_ribbon(cv, W, H):
    D = cv.d
    cv.rect(9, 2.2, D["ribbon"], W, H)
    cv.rect(12.2, 0.6, D["accent"], W, H)
    cv.rect(13.4, 0.25, D["accent"], W, H)


def draw_medal(cv, cx, top, size, logo=None):
    """금메달 + 리본 꼬리. cx/top/size 는 px. 로고가 있으면 메달 가운데에."""
    D, d = cv.d, cv.draw
    R = size * 0.36
    cy = top + R * 1.15
    rib = D["ribbon"]
    dark_rib = tuple(int(v * 0.7) for v in rib)
    for sgn in (-1, 1):  # 꼬리 두 갈래
        x0 = cx + sgn * R * 0.25
        x1 = cx + sgn * R * 0.95
        y1 = top + size
        d.polygon([(x0 - sgn * R * 0.2, cy), (x0 + sgn * R * 0.35, cy), (x1, y1), (x1 - sgn * R * 0.32, y1 - R * 0.28), (x1 - sgn * R * 0.6, y1)],
                  fill=rib if sgn < 0 else dark_rib)
    n = 36
    pts = [(cx + (R if i % 2 == 0 else R * 0.88) * math.cos(i * math.pi / n), cy + (R if i % 2 == 0 else R * 0.88) * math.sin(i * math.pi / n))
           for i in range(2 * n)]
    d.polygon(pts, fill=D["accent"], outline=D["dark"])
    for rr, col in ((0.8, D["dark"]), (0.76, (226, 192, 104)), (0.62, D["accent"])):
        r = R * rr
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    r = R * 0.62
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=D["dark"], width=max(1, cv.px(0.35)))
    if logo is not None:
        lg = fit(logo, int(R * 0.95), int(R * 0.95))
        d.ellipse([cx - R * 0.58, cy - R * 0.58, cx + R * 0.58, cy + R * 0.58], fill=(255, 250, 236))
        paste_image(cv.img, lg, (int(cx - lg.width / 2), int(cy - lg.height / 2)))
    else:  # 별
        sr = R * 0.45
        star = [(cx + (sr if i % 2 == 0 else sr * 0.42) * math.cos(-math.pi / 2 + i * math.pi / 5),
                 cy + (sr if i % 2 == 0 else sr * 0.42) * math.sin(-math.pi / 2 + i * math.pi / 5)) for i in range(10)]
        d.polygon(star, fill=(250, 228, 160), outline=D["dark"])


# 금속 광택 금색: 짙은 금 → 밝은 금 → 하이라이트 → 중간 → 짙은 금 을 대각선 방향으로 몇 번 반복
GOLD_STOPS = [(0.00, (128, 92, 30)), (0.18, (186, 146, 64)), (0.34, (238, 214, 146)), (0.42, (252, 238, 190)),
              (0.52, (214, 176, 96)), (0.70, (160, 118, 42)), (0.84, (204, 164, 82)), (1.00, (128, 92, 30))]


def _gold_lut():
    luts = ([], [], [])
    for v in range(256):
        t = v / 255
        for (t0, c0), (t1, c1) in zip(GOLD_STOPS, GOLD_STOPS[1:]):
            if t0 <= t <= t1:
                f = (t - t0) / (t1 - t0) if t1 > t0 else 0
                for i in range(3):
                    luts[i].append(int(c0[i] + (c1[i] - c0[i]) * f))
                break
    return luts


GOLD_LUT = _gold_lut()


def gold_texture(size, cycles=2.5, angle=(0.82, 0.36)):
    """금속 광택 RGB 이미지 — 작은 크기로 계산해 키운다(빠름)"""
    w, h = size
    sw, sh = max(8, w // 10), max(8, h // 10)
    ax, ay = angle
    span = ax * sw + ay * sh
    g = Image.new("L", (sw, sh))
    g.putdata([int(255 * ((((ax * x + ay * y) / span) * cycles) % 1.0)) for y in range(sh) for x in range(sw)])
    # 톱니 끝 이음매가 끊기지 않게 삼각파로 접기
    g = g.point(lambda v: min(255, 2 * v) if v < 128 else min(255, 2 * (255 - v)))
    g = g.resize((w, h), Image.BILINEAR)
    return Image.merge("RGB", [g.point(l) for l in GOLD_LUT])


def paint_gold(cv, mask, shadow=True):
    """mask(L, 페이지 크기)의 자리에 금속 금색을 칠한다. shadow: 아주 옅은 그림자로 띠가 살짝 떠 보이게"""
    img = cv.img
    if shadow:
        sh = mask.filter(ImageFilter.GaussianBlur(cv.px(0.5))).point(lambda v: int(v * 0.16))
        off = Image.new("L", mask.size, 0)
        off.paste(sh, (cv.px(0.35), cv.px(0.45)))
        img.paste((90, 70, 40), (0, 0), off)
    img.paste(gold_texture(img.size), (0, 0), mask)


def deco_goldframe(cv, W, H):
    """흰 바탕 금테: 바깥 굵은 금선 + 안쪽 가는 금선, 장식 없음"""
    m = Image.new("L", cv.img.size, 0)
    d = ImageDraw.Draw(m)
    for inset, wmm in ((9.0, 3.2), (14.2, 0.7), (15.6, 0.3)):
        i, w = cv.px(inset), max(1, cv.px(wmm))
        d.rectangle([i, i, cv.px(W) - i - 1, cv.px(H) - i - 1], outline=255, width=w)
    paint_gold(cv, m, shadow=False)


def deco_goldcorner(cv, W, H):
    """모서리 금띠: 영정 액자 모서리 리본처럼 모서리만 대각선으로 가로지르는 금색 띠(굵은 띠 + 가는 띠 둘)"""
    corners = ("tl", "br") if str(getattr(cv, "cfg", {}).get("corners") or "4") == "2" else ("tl", "tr", "bl", "br")
    s = min(W, H) / 210  # 가로형에서도 같은 비율
    bands = [(22 * s, 36 * s), (39 * s, 41.2 * s), (43.6 * s, 44.4 * s)]  # 모서리에서 x+y 거리(mm) 구간
    m = Image.new("L", cv.img.size, 0)
    d = ImageDraw.Draw(m)
    PW, PH = cv.px(W), cv.px(H)
    for a, b in bands:
        A, B = cv.px(a), cv.px(b)
        for c in corners:
            pts = [(A, 0), (B, 0), (0, B), (0, A)]
            pts = [((PW - x) if c in ("tr", "br") else x, (PH - y) if c in ("bl", "br") else y) for x, y in pts]
            d.polygon(pts, fill=255)
    i = cv.px(10)  # 아주 옅은 안쪽 테두리 (금띠 아래로 지나가게 먼저)
    cv.draw.rectangle([i, i, PW - i - 1, PH - i - 1], outline=(236, 226, 204), width=max(1, cv.px(0.25)))
    paint_gold(cv, m)


DECO = {"traditional": deco_traditional, "official": deco_official, "modern": deco_modern, "hanji": deco_hanji, "ribbon": deco_ribbon,
        "goldframe": deco_goldframe, "goldcorner": deco_goldcorner}


# ── 본문 줄바꿈 ──────────────────────────────────────────────────────────
def wrap(text, fnt, width):
    """어절 단위 줄바꿈(긴 어절은 글자 단위). 문단(\n) 유지. → [(words, is_last_of_paragraph)]"""
    out = []
    sw = fnt.getlength(" ")
    for para in (text or "").split("\n"):
        words = para.split()
        if not words:
            out.append(([], True))
            continue
        line, lw = [], 0
        for wd in words:
            ww = fnt.getlength(wd)
            if ww > width:  # 한 어절이 너무 길면 글자 단위로 쪼갬
                chunk = ""
                for ch in wd:
                    if fnt.getlength(chunk + ch) > width:
                        line.append(chunk) if chunk else None
                        out.append((line, False))
                        line, chunk = [], ""
                    chunk += ch
                wd, ww = chunk, fnt.getlength(chunk)
                lw = sum(fnt.getlength(x) for x in line) + sw * len(line)
            add = ww + (sw if line else 0)
            if line and lw + add > width:
                out.append((line, False))
                line, lw = [wd], ww
            else:
                line.append(wd)
                lw += add
        out.append((line, True))
    return out


def draw_justified(cv, lines, fnt, x0, width, y, lh, fill):
    """양쪽 맞춤: 남는 폭을 글자 사이에 고르게 (한 줄이 너무 성기면 왼쪽 맞춤)"""
    for words, last in lines:
        if words:
            s = " ".join(words)
            nat = fnt.getlength(s)
            extra = (width - nat) / (len(s) - 1) if len(s) > 1 and not last else 0
            if extra > fnt.size * 0.25:
                extra = 0
            if extra <= 0:
                cv.draw.text((x0, y), s, font=fnt, fill=fill, anchor="ls")
            else:
                x = x0
                for ch in s:
                    cv.draw.text((x, y), ch, font=fnt, fill=fill, anchor="ls")
                    x += fnt.getlength(ch) + extra
        y += lh
    return y


# ── 본 렌더 ─────────────────────────────────────────────────────────────
def render(c, dpi=300, logo=None, seal=None):
    """c: dict(design, orient, kind, award, number, name, dept, position, text, date, org, giver_title, giver_name,
    seal_mode(auto-square|auto-round|upload|none), seal_text, logo_mode(top|watermark|none))
    logo/seal: PIL.Image 또는 None (업로드 파일)"""
    D = DESIGNS.get(c.get("design"), DESIGNS["traditional"])
    land = c.get("orient") == "landscape"
    W, H = (297, 210) if land else (210, 297)
    img = Image.new("RGB", (int(round(W * dpi / 25.4)), int(round(H * dpi / 25.4))), D["paper"])
    cv = Canvas(img, dpi, D)
    cv.cfg = c
    DECO[next(k for k, v in DESIGNS.items() if v is D)](cv, W, H)
    is_ribbon, is_modern = D is DESIGNS["ribbon"], D is DESIGNS["modern"]
    pad = D["pad"]
    x0 = pad + (6 if is_modern else 0)
    x1 = W - pad
    cx = cv.px((x0 + x1) / 2)
    ink = D["ink"]
    logo_mode = c.get("logo_mode") or "top"

    if logo is not None and logo_mode == "watermark":
        wm = fit(ImageOps.exif_transpose(logo), cv.px((x1 - x0) * 0.62), cv.px(H * 0.42))
        paste_image(img, wm, (cx - wm.width // 2, cv.px(H * 0.52) - wm.height // 2), opacity=0.09)

    y = pad  # mm, 위에서부터 흐름
    num = number_label(c.get("number"))
    if num:
        cv.text(cv.px(x0), cv.px(y + 4), num, cv.f(D["font"], 4.0), ink)
    y += 7

    if is_ribbon:
        ms = 30 if land else 44
        draw_medal(cv, cx, cv.px(y - 4), cv.px(ms), logo if logo_mode == "top" else None)
        y += ms - 2
    elif logo is not None and logo_mode == "top":
        lh = 13 if land else 18
        lg = fit(ImageOps.exif_transpose(logo), cv.px(70), cv.px(lh))
        paste_image(img, lg, (cx - lg.width // 2, cv.px(y)))
        y += lh + 4

    # 제목 (상장·표창장…) — 글자 수가 적을수록 넓게 띄움
    title = re.sub(r"\s+", "", c.get("kind") or "상장")
    n = len(title)
    ts = (16 if land else 21) * (1 if n <= 3 else 0.85 if n <= 5 else 0.7)
    gap_em = {1: 0, 2: 1.4, 3: 0.75, 4: 0.35}.get(n, 0.12)
    while True:
        tf = cv.f(D["tfont"], ts)
        gap = gap_em * ts * cv.k
        if cv.w(title, tf, gap) <= cv.px(x1 - x0) or ts < 6:
            break
        ts *= 0.92
    base = y + ts * 0.9
    cv.text(cx, cv.px(base), title, tf, D["title"], anchor="ms", gap=gap)
    y = base + ts * 0.28
    if is_modern:
        cap = CAPTION.get(title, "CERTIFICATE")
        cf = cv.f(GTB, 3.0)
        y += 5
        cv.text(cx, cv.px(y), cap, cf, D["accent"], anchor="ms", gap=cv.px(1.1))
        y += 2
    elif D is DESIGNS["official"]:
        y += 2.5
        cv.draw.line([(cx - cv.px(28), cv.px(y)), (cx + cv.px(28), cv.px(y))], fill=D["accent"], width=max(1, cv.px(0.7)))
        cv.draw.line([(cx - cv.px(28), cv.px(y + 1.2)), (cx + cv.px(28), cv.px(y + 1.2))], fill=D["accent"], width=max(1, cv.px(0.25)))
        y += 1.5
    award = (c.get("award") or "").strip()
    if award:
        y += 9 if not land else 7.5
        af = cv.f(D["bold"], 6.2 if not land else 5.4)
        while cv.w(award, af) > cv.px(x1 - x0) and af.size > 8:
            af = font(D["bold"], af.size * 0.92)
        cv.text(cx, cv.px(y), award, af, D["title"], anchor="ms")
    y += 12 if not land else 7

    # 수상자: 소 속 / 직 위 / 성 명
    rows = [(lab, v) for lab, v in (("소 속", c.get("dept")), ("직 위", c.get("position")), ("성 명", spaced_name(c.get("name")))) if (v or "").strip()]
    if rows:
        lf, vf, nf = cv.f(D["font"], 5.0), cv.f(D["font"], 5.2), cv.f(D["bold"], 6.4 if not land else 6.0)
        lab_w = max(cv.w(lab, lf) for lab, _ in rows)
        g = cv.px(5)
        val_w = max(cv.w(v, nf if lab == "성 명" else vf) for lab, v in rows)
        bw = lab_w + g + val_w
        bx = max(cv.px(x0), min(cv.px(W * 0.53 if not land else W * 0.56), cv.px(x1 - 4) - bw))
        if land and len(rows) > 1:  # 가로형은 한 줄로
            parts = [(lab.replace(" ", ""), v) for lab, v in rows]
            seg = [(lab, v, nf if lab == "성명" else vf) for lab, v in parts]
            tot = sum(cv.w(lab, lf) + cv.px(2.5) + cv.w(v, f) for lab, v, f in seg) + cv.px(9) * (len(seg) - 1)
            x = cx - tot / 2
            y += 5
            for lab, v, f in seg:
                cv.text(x, cv.px(y), lab, lf, ink)
                x += cv.w(lab, lf) + cv.px(2.5)
                cv.text(x, cv.px(y), v, f, ink)
                x += cv.w(v, f) + cv.px(9)
            y += 3
        else:
            for lab, v in rows:
                rh = 9.5 if lab == "성 명" else 8.5
                y += rh
                cv.text(bx, cv.px(y), lab, lf, ink, gap=0)
                cv.text(bx + lab_w + g, cv.px(y), v, nf if lab == "성 명" else vf, ink)
            y += 2

    # 아래에서부터: 서명(기관장)·날짜
    sig_y = H - pad - (9 if land else 15)
    date_y = sig_y - (15 if land else 22)
    body_top, body_bot = y + (9 if land else 14), date_y - (10 if land else 16)

    # 본문
    text = (c.get("text") or "").strip()
    bs = 8.0 if not land else 7.0
    bfont = D["bold"] if D is DESIGNS["hanji"] or D is DESIGNS["traditional"] else D["font"]
    margin_in = 6 if not land else 18
    bw_px = cv.px(x1 - x0 - 2 * margin_in)
    while True:
        bf = cv.f(bfont, bs)
        lines = wrap(text, bf, bw_px)
        lh = bs * (1.95 if not land else 1.8)
        need = len(lines) * lh
        if need <= body_bot - body_top or bs < 3.2:
            break
        bs *= 0.94
    ystart = body_top + max(0, (body_bot - body_top - need) / 2) + bs * 0.95
    draw_justified(cv, lines, bf, cv.px(x0 + margin_in), bw_px, cv.px(ystart), cv.px(lh), ink)

    cv.text(cx, cv.px(date_y), kdate(c.get("date")), cv.f(D["font"], 5.4), ink, anchor="ms", gap=cv.px(0.3))

    org = (c.get("org") or "").strip()
    gt = (c.get("giver_title") or "").strip()
    gn = spaced_name(c.get("giver_name"))
    sig = "  ".join(p for p in (org, gt, gn) if p)
    sf = cv.f(D["bold"], 7.4 if not land else 6.8)
    while cv.w(sig, sf, cv.px(0.6)) > cv.px(x1 - x0 - 30) and sf.size > 10:
        sf = font(D["bold"], sf.size * 0.94)
    seal_mm = 22 if not land else 19
    sw = cv.w(sig, sf, cv.px(0.6))
    sx = cx - (sw + cv.px(seal_mm * 0.55)) / 2  # 도장 자리까지 합쳐 가운데
    cv.text(sx, cv.px(sig_y), sig, sf, ink, anchor="ls", gap=cv.px(0.6))

    mode = c.get("seal_mode") or "auto-square"
    st = None
    if mode == "upload" and seal is not None:
        st = fit(prepare_upload_seal(seal), cv.px(seal_mm), cv.px(seal_mm))
    elif mode in ("auto-square", "auto-round"):
        txt = (c.get("seal_text") or "").strip() or seal_text_auto(org, gt)
        st = make_seal(txt, "round" if mode == "auto-round" else "square", cv.px(seal_mm))
    if st is not None:
        scy = cv.px(sig_y) - sf.size * 0.38
        _alpha_paste(img, st, (int(sx + sw - st.width * 0.06), int(scy - st.height / 2)))
    return img


def png_bytes(img, dpi=300):
    b = io.BytesIO()
    img.save(b, "PNG", dpi=(dpi, dpi), optimize=False)
    return b.getvalue()


def pdf_bytes(imgs, dpi=300):
    b = io.BytesIO()
    imgs[0].save(b, "PDF", resolution=dpi, save_all=True, append_images=imgs[1:], quality=92)
    return b.getvalue()
