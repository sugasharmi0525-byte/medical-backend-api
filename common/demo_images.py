"""Generates placeholder PNGs for demo seed data (no real photos or product artwork)."""

import io

from django.core.files.base import ContentFile
from PIL import Image, ImageDraw, ImageFont


def _font(size):
    return ImageFont.load_default(size=size)


def _png(image, filename):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return ContentFile(buffer.getvalue(), name=filename)


def _vertical_gradient(size, top, bottom):
    width, height = size
    image = Image.new("RGB", size, top)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / max(height - 1, 1)
        color = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom, strict=True))
        draw.line([(0, y), (width, y)], fill=color)
    return image


def avatar_image(initials, background, filename, caption="DEMO"):
    """Square avatar with initials, e.g. for doctor / patient profile photos."""
    size = 400
    image = Image.new("RGB", (size, size), background)
    draw = ImageDraw.Draw(image)
    draw.ellipse([60, 40, 340, 320], fill=tuple(min(c + 40, 255) for c in background))
    draw.text((size / 2, 180), initials.upper(), fill="white", font=_font(120), anchor="mm")
    draw.text((size / 2, 365), caption, fill="white", font=_font(28), anchor="mm")
    return _png(image, filename)


def product_image(title, subtitle, top, bottom, filename, label="NEURO LIFE", shape="bottle"):
    """Product shot placeholder: a labelled bottle, carton or jar on a gradient background."""
    width, height = 800, 800
    image = _vertical_gradient((width, height), top, bottom)
    draw = ImageDraw.Draw(image)
    white = (250, 250, 252)
    if shape == "box":
        # carton with a lid edge and a coloured band
        draw.polygon([(250, 230), (300, 180), (600, 180), (550, 230)], fill=(225, 228, 236))
        draw.polygon([(550, 230), (600, 180), (600, 600), (550, 650)], fill=(205, 210, 222))
        draw.rectangle([250, 230, 550, 650], fill=white)
        draw.rectangle([250, 340, 550, 540], fill=top)
        cx, band = 400, (340, 540)
    elif shape == "jar":
        draw.rounded_rectangle([280, 200, 520, 270], radius=14, fill=(40, 40, 60))
        draw.rounded_rectangle([250, 260, 550, 650], radius=60, fill=white)
        draw.rectangle([250, 350, 550, 550], fill=top)
        cx, band = 400, (350, 550)
    else:
        draw.rounded_rectangle([340, 150, 460, 220], radius=12, fill=(40, 40, 60))
        draw.rounded_rectangle([270, 210, 530, 650], radius=40, fill=white)
        draw.rectangle([270, 330, 530, 530], fill=top)
        cx, band = 400, (330, 530)
    mid = (band[0] + band[1]) / 2
    draw.text((cx, mid - 45), "MEDICINE", fill="white", font=_font(34), anchor="mm")
    draw.text(
        (cx, mid + 5), label, fill="white", font=_font(30 if len(label) <= 12 else 24), anchor="mm"
    )
    draw.text((cx, mid + 50), "DEMO", fill="white", font=_font(22), anchor="mm")
    draw.text((width / 2, 715), title, fill="white", font=_font(40), anchor="mm")
    draw.text((width / 2, 760), subtitle, fill="white", font=_font(24), anchor="mm")
    return _png(image, filename)


def report_pdf(title, patient_name, rows, filename):
    """One-page 'lab report' PDF with a table of fictional values."""
    width, height = 1240, 1754  # A4 at 150 dpi
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, width, 170], fill=(15, 118, 110))
    draw.text((80, 60), "MEDICINE DIAGNOSTICS (DEMO)", fill="white", font=_font(44))
    draw.text(
        (80, 120), "Sample report - fictional values for testing only", fill="white", font=_font(24)
    )
    draw.text((80, 230), title, fill=(15, 23, 42), font=_font(40))
    draw.text((80, 290), f"Patient: {patient_name}", fill=(71, 85, 105), font=_font(28))
    y = 380
    draw.rectangle([80, y, width - 80, y + 60], fill=(240, 253, 250))
    for x, heading in zip((100, 560, 860), ("Test", "Result", "Reference range"), strict=True):
        draw.text((x, y + 15), heading, fill=(15, 118, 110), font=_font(28))
    y += 80
    for test, result, reference in rows:
        draw.text((100, y), test, fill=(30, 41, 59), font=_font(26))
        draw.text((560, y), result, fill=(30, 41, 59), font=_font(26))
        draw.text((860, y), reference, fill=(100, 116, 139), font=_font(26))
        draw.line([(80, y + 50), (width - 80, y + 50)], fill=(226, 232, 240), width=2)
        y += 70
    draw.text(
        (80, height - 120),
        "DEMO DOCUMENT - NOT A REAL MEDICAL RECORD",
        fill=(220, 38, 38),
        font=_font(30),
    )
    buffer = io.BytesIO()
    image.save(buffer, format="PDF", resolution=150)
    return ContentFile(buffer.getvalue(), name=filename)


def scan_image(label, filename):
    """Dark 'scan' placeholder with a stylised brain outline."""
    size = 800
    image = Image.new("RGB", (size, size), (10, 14, 26))
    draw = ImageDraw.Draw(image)
    for radius, shade in ((300, 30), (260, 45), (220, 60)):
        draw.ellipse(
            [
                size / 2 - radius,
                size / 2 - radius * 0.8,
                size / 2 + radius,
                size / 2 + radius * 0.8,
            ],
            outline=(shade * 2, shade * 3, shade * 4),
            width=6,
        )
    draw.line([(size / 2, 130), (size / 2, 670)], fill=(90, 130, 170), width=4)
    for offset in (-150, -80, 80, 150):
        draw.arc(
            [size / 2 + offset - 60, 250, size / 2 + offset + 60, 550],
            60,
            300,
            fill=(120, 170, 210),
            width=4,
        )
    draw.text((30, 30), label, fill=(200, 220, 240), font=_font(30))
    draw.text((30, size - 60), "DEMO IMAGE - NOT A REAL SCAN", fill=(248, 113, 113), font=_font(26))
    return _png(image, filename)
