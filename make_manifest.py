#!/usr/bin/env python3
"""Analyse every photo in images/ and write photos.json.

Optional high-res versions: put a copy with the same name in images/full/
(e.g. images/IMG_01.jpg + images/full/IMG_01.jpg). The gallery uses the
file in images/; clicking a photo loads the one in images/full/ if it exists.

For each photo this stores its position on the colour scope, brightness,
a 5-colour palette and a small pixel sample for the scope trace, so the
page never has to download full images just to analyse them.
Unchanged photos are reused from the previous photos.json (matched by hash).

Requires: pip install pillow
"""
import base64, hashlib, json, pathlib
from PIL import Image, ImageOps

EXT = {".webp", ".jpg", ".jpeg", ".png", ".avif"}
VERSION = 2            # bump to force re-analysis of everything
K = 3.4                # scope zoom (must match index.html)
AW, AH = 80, 53        # size used for position / brightness / palette
TW, TH = 40, 27        # size of the pixel sample used to draw the trace

root = pathlib.Path(__file__).parent
out = root / "photos.json"


def ycc(r, g, b):
    r, g, b = r / 255, g / 255, b / 255
    return (.299 * r + .587 * g + .114 * b,
            -.168736 * r - .331264 * g + .5 * b,
            .5 * r - .418688 * g - .081312 * b)


def palette(px, k=5):
    lum = lambda c: .299 * c[0] + .587 * c[1] + .114 * c[2]
    S = sorted(px[::max(1, len(px) // 1200)], key=lum)
    C = [list(S[int((i + .5) / k * len(S))]) for i in range(k)]
    for _ in range(10):
        sums = [[0, 0, 0, 0] for _ in range(k)]
        for c in S:
            j = min(range(k), key=lambda j: (c[0]-C[j][0])**2 + (c[1]-C[j][1])**2 + (c[2]-C[j][2])**2)
            s = sums[j]; s[0] += c[0]; s[1] += c[1]; s[2] += c[2]; s[3] += 1
        C = [[s[0]/s[3], s[1]/s[3], s[2]/s[3]] if s[3] else C[i] for i, s in enumerate(sums)]
    return [[round(v) for v in c] for c in sorted(C, key=lum)]


def analyse(path):
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    raw = im.resize((AW, AH), Image.BOX).tobytes()
    px = list(zip(raw[0::3], raw[1::3], raw[2::3]))
    sb = sr = sk = sy = 0.0
    ys = []
    for r, g, b in px:
        Y, Cb, Cr = ycc(r, g, b)
        ys.append(Y)
        k = (Cb * Cb + Cr * Cr) ** .5
        sy += Y; sb += Cb * k; sr += Cr * k; sk += k
    n = len(px)
    p = [0, 0] if sk / n < .02 else [round(sb / sk * K, 4), round(-sr / sk * K, 4)]
    trace = base64.b64encode(im.resize((TW, TH), Image.BOX).tobytes()).decode()
    ys.sort()
    contrast = ys[int(.95 * (n - 1))] - ys[int(.05 * (n - 1))]   # spread of the middle 90% of tones
    return {"p": p, "y": round(sy / n, 4), "k": round(sy / n, 4), "c": round(contrast, 4),
            "pal": palette(px), "tr": trace}


old = {}
if out.exists():
    try:
        old = {e["src"]: e for e in json.loads(out.read_text())}
    except Exception:
        pass

entries, done = [], 0
FULL = root / "images" / "full"   # optional high-res copies, same name as the gallery photo
fulls = {p.stem.lower(): p for p in FULL.glob("*") if p.suffix.lower() in EXT} if FULL.exists() else {}
files = sorted(p for p in (root / "images").rglob("*")
               if p.suffix.lower() in EXT and FULL not in p.parents)
for f in files:
    src = f.relative_to(root).as_posix()
    h = hashlib.md5(f.read_bytes()).hexdigest()[:10]
    e = old.get(src)
    if not (e and e.get("h") == h and e.get("v") == VERSION):
        try:
            e = {"src": src, "h": h, "v": VERSION, **analyse(f)}
        except Exception as ex:
            print(f"skipped {src}: {ex}")
            continue
        done += 1
    full = fulls.get(f.stem.lower())
    e = {k: v for k, v in e.items() if k != "full"}
    if full:
        e["full"] = full.relative_to(root).as_posix()
    entries.append(e)

out.write_text("[\n" + ",\n".join(json.dumps(e, separators=(",", ":")) for e in entries) + "\n]\n")
print(f"photos.json: {len(entries)} photos, {sum('full' in e for e in entries)} with a full-size version ({done} analysed, {len(entries) - done} reused)")