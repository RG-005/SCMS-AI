"""
Demo photos for the seed tickets (Sprint 3 point 7, deploy).

The seed reports point at photos that never existed, so a fresh deployment showed
"Foto tidak tersedia" everywhere. These are generated illustrations of asphalt damage,
not real evidence: every image carries a "FOTO DEMO" label so nobody mistakes it for a
citizen's photo. They live in app/static/demo/ (part of the image), not in
app/static/uploads/ (the uploads volume).

Regenerate with:  python -m database.foto_demo
Replace them with real field photos by saving JPEGs under the same names.
"""
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FOLDER = Path(__file__).resolve().parent.parent / "app" / "static" / "demo"
UKURAN = (1280, 960)

# file name -> (kind of damage, caption)
FOTO = {
    "jalan_berlubang_kertajaya.jpg": ("lubang", "Jl. Raya Kertajaya - jalan berlubang"),
    "jalan_berlubang_sudirman.jpg": ("lubang_kecil", "Jl. Sudirman - jalan berlubang"),
    "retak_dharmahusada.jpg": ("retak", "Jl. Dharmahusada - retak permukaan"),
    "selesai_dharmahusada.jpg": ("tambalan", "Jl. Dharmahusada - setelah perbaikan"),
}


def _aspal(rng: random.Random) -> Image.Image:
    lebar, tinggi = UKURAN
    dasar = Image.new("RGB", UKURAN, (78, 80, 82))
    noise = Image.effect_noise(UKURAN, 38).convert("RGB")
    img = Image.blend(dasar, noise, 0.32)
    draw = ImageDraw.Draw(img)
    # aggregate stones
    for _ in range(9000):
        x, y = rng.randrange(lebar), rng.randrange(tinggi)
        g = rng.randrange(55, 125)
        r = rng.choice((1, 1, 1, 2))
        draw.ellipse((x, y, x + r, y + r), fill=(g, g, g + rng.randrange(-4, 5)))
    # worn lane marking in perspective
    for i in range(6):
        y0 = 60 + i * 160
        w = 26 + i * 6
        draw.polygon([(lebar * 0.5 - w / 2, y0), (lebar * 0.5 + w / 2, y0),
                      (lebar * 0.5 + w / 2 + 4, y0 + 95), (lebar * 0.5 - w / 2 - 4, y0 + 95)],
                     fill=(196, 192, 170))
    return img.filter(ImageFilter.GaussianBlur(0.6))


def _lubang(img: Image.Image, rng: random.Random, cx: float, cy: float, rx: float, ry: float):
    draw = ImageDraw.Draw(img)
    titik = []
    for i in range(48):
        sudut = 2 * math.pi * i / 48
        k = 1 + rng.uniform(-0.18, 0.18)
        titik.append((cx + rx * k * math.cos(sudut), cy + ry * k * math.sin(sudut)))
    draw.polygon(titik, fill=(52, 50, 47))                         # broken edge
    dalam = [(cx + (x - cx) * 0.82, cy + (y - cy) * 0.82 + 6) for x, y in titik]
    draw.polygon(dalam, fill=(34, 32, 30))                          # hole
    genangan = [(cx + (x - cx) * 0.55, cy + (y - cy) * 0.45 + 14) for x, y in titik]
    draw.polygon(genangan, fill=(58, 66, 74))                       # puddle
    for _ in range(260):                                            # loose gravel
        a, d = rng.uniform(0, 2 * math.pi), rng.uniform(0.9, 1.35)
        x, y = cx + rx * d * math.cos(a), cy + ry * d * math.sin(a)
        g = rng.randrange(90, 150)
        draw.ellipse((x, y, x + 3, y + 3), fill=(g, g, g))


def _retak(img: Image.Image, rng: random.Random):
    draw = ImageDraw.Draw(img)
    for awal in ((120, 520), (300, 300), (700, 700)):
        x, y = awal
        for _ in range(70):
            nx, ny = x + rng.uniform(4, 16), y + rng.uniform(-10, 10)
            draw.line((x, y, nx, ny), fill=(30, 30, 30), width=rng.choice((2, 3, 4)))
            if rng.random() < 0.12:                                  # branch
                draw.line((nx, ny, nx + rng.uniform(-30, 30), ny + rng.uniform(15, 45)), fill=(36, 36, 36), width=2)
            x, y = nx, ny


def _tambalan(img: Image.Image, rng: random.Random):
    draw = ImageDraw.Draw(img)
    draw.rectangle((180, 330, 1050, 640), fill=(46, 47, 49))         # fresh hotmix
    for _ in range(2500):
        x, y = rng.randrange(180, 1050), rng.randrange(330, 640)
        g = rng.randrange(40, 70)
        draw.point((x, y), fill=(g, g, g))
    draw.rectangle((180, 330, 1050, 640), outline=(30, 30, 30), width=4)


def _label(img: Image.Image, keterangan: str):
    draw = ImageDraw.Draw(img, "RGBA")
    try:
        besar = ImageFont.truetype("DejaVuSans-Bold.ttf", 34)
        kecil = ImageFont.truetype("DejaVuSans.ttf", 24)
    except OSError:
        besar = kecil = ImageFont.load_default()
    draw.rectangle((0, UKURAN[1] - 92, UKURAN[0], UKURAN[1]), fill=(15, 41, 66, 215))
    draw.text((28, UKURAN[1] - 84), "FOTO DEMO - SCMS-AI", font=besar, fill=(255, 255, 255))
    draw.text((28, UKURAN[1] - 40), f"Ilustrasi untuk data contoh, bukan foto lapangan. {keterangan}",
              font=kecil, fill=(210, 222, 236))


def buat_foto_demo(folder: Path = FOLDER) -> list:
    folder.mkdir(parents=True, exist_ok=True)
    hasil = []
    for i, (nama, (jenis, keterangan)) in enumerate(FOTO.items()):
        rng = random.Random(2026 + i)          # same pixels on every run
        img = _aspal(rng)
        if jenis == "lubang":
            _lubang(img, rng, 520, 470, 250, 150)
        elif jenis == "lubang_kecil":
            _lubang(img, rng, 760, 520, 150, 95)
            _lubang(img, rng, 380, 330, 90, 55)
        elif jenis == "retak":
            _retak(img, rng)
        elif jenis == "tambalan":
            _tambalan(img, rng)
        _label(img, keterangan)
        tujuan = folder / nama
        img.save(tujuan, "JPEG", quality=82, optimize=True)
        hasil.append(tujuan)
    return hasil


if __name__ == "__main__":
    for path in buat_foto_demo():
        print(f"{path.relative_to(FOLDER.parent.parent.parent)}  {path.stat().st_size // 1024} KB")
