"""Draw docs/er_overview.png: the tables grouped by domain, each row listing the tables it references.

Reads docs/schema.json (run export_schema.py first).
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
S = 2
F = "C:/Windows/Fonts/"
TITLE = ImageFont.truetype(F + "arialbd.ttf", 16 * S)
HEAD = ImageFont.truetype(F + "arialbd.ttf", 14 * S)
SUB = ImageFont.truetype(F + "ariali.ttf", 10 * S)
NAME = ImageFont.truetype(F + "consolab.ttf", 11 * S)
REF = ImageFont.truetype(F + "consola.ttf", 10 * S)
LBL = ImageFont.truetype(F + "arial.ttf", 10 * S)
INK, GREY, LINE = (30, 38, 52), (110, 118, 132), (120, 128, 142)

COLS = [40, 600, 1160]
CARD_W, ROW_H, HEAD_H = 520, 21, 50
GRID = [["org", "case", "reference"], ["research", "teaching", "service"], ["assessment", "referees", "audit"]]
COLOURS = {"org": (52, 101, 164), "case": (122, 90, 22), "reference": (86, 110, 61), "research": (46, 120, 130),
           "teaching": (46, 120, 130), "service": (46, 120, 130), "assessment": (140, 70, 70),
           "referees": (110, 80, 140), "audit": (90, 90, 90)}
SHORT = {"promotion_case": "case", "app_user": "user"}
HIDDEN_REFS = {"lookup_value"}  # referenced by many tables; stated once in the legend


def main() -> None:
    data = json.loads((ROOT / "docs" / "schema.json").read_text(encoding="utf-8"))
    by_mod = {}
    for t in data["tables"]:
        by_mod.setdefault(t["module"], []).append(t)
    titles = {d["module"]: (d["title"], d["spec"]) for d in data["domains"]}

    img = Image.new("RGB", (1720 * S, 1900 * S), "white")
    d = ImageDraw.Draw(img)
    d.text((40 * S, 22 * S), f"PromoFlow database – domain overview ({len(data['tables'])} tables)", font=TITLE, fill=INK)
    d.text((40 * S, 48 * S), "Each row: table  → tables it references (case = promotion_case, user = app_user). "
           "Dropdown links to lookup_value and file links through case_document are not shown.", font=SUB, fill=GREY)

    boxes, y = {}, 90
    for row in GRID:
        row_h = max(HEAD_H + ROW_H * len(by_mod[m]) + 14 for m in row)
        for x, mod in zip(COLS, row):
            tables, colour = by_mod[mod], COLOURS[mod]
            h = HEAD_H + ROW_H * len(tables) + 14
            boxes[mod] = (x, y, x + CARD_W, y + h)
            d.rounded_rectangle([x * S, y * S, (x + CARD_W) * S, (y + h) * S], radius=8 * S, fill="white",
                                outline=colour, width=2 * S)
            d.rounded_rectangle([x * S, y * S, (x + CARD_W) * S, (y + HEAD_H) * S], radius=8 * S, fill=colour)
            d.rectangle([x * S, (y + HEAD_H - 10) * S, (x + CARD_W) * S, (y + HEAD_H) * S], fill=colour)
            title, spec = titles[mod]
            d.text(((x + 12) * S, (y + 7) * S), f"{title} ({len(tables)})", font=HEAD, fill="white")
            d.text(((x + 12) * S, (y + 28) * S), spec, font=SUB, fill=(235, 238, 242))
            for i, t in enumerate(tables):
                ty = y + HEAD_H + 7 + i * ROW_H
                d.text(((x + 14) * S, ty * S), t["name"], font=NAME, fill=INK)
                refs = [SHORT.get(r, r) for r in t["refs"] if r not in HIDDEN_REFS]
                if refs:
                    nx = x + 14 + d.textlength(t["name"], font=NAME) / S + 8
                    d.text((nx * S, (ty + 1) * S), "→ " + ", ".join(refs), font=REF, fill=GREY)
        y += row_h + 70

    def hline(a, b, yy, label):
        d.line([a * S, yy * S, b * S, yy * S], fill=LINE, width=2 * S)
        tip = b if b > a else b
        sgn = 1 if b > a else -1
        d.polygon([(tip * S, yy * S), ((tip - 10 * sgn) * S, (yy - 6) * S), ((tip - 10 * sgn) * S, (yy + 6) * S)],
                  fill=LINE)
        w = d.textlength(label, font=LBL) / S
        d.text((((a + b) / 2 - w / 2) * S, (yy + 6) * S), label, font=LBL, fill=INK)

    # case -> org (applicant) and case -> reference (policy version): short horizontal arrows
    cy = boxes["case"][1] + 30
    hline(boxes["case"][0], boxes["org"][2], cy + 40, "applicant")
    hline(boxes["case"][2], boxes["reference"][0], cy + 40, "policy")

    # dossier groups -> case: a bus under the case card
    bus_y = boxes["case"][3] + 32
    top_row2 = boxes["research"][1]
    xs = [(boxes[m][0] + boxes[m][2]) / 2 for m in ("research", "teaching", "service")]
    d.line([xs[0] * S, bus_y * S, xs[2] * S, bus_y * S], fill=LINE, width=2 * S)
    for x in xs:
        d.line([x * S, bus_y * S, x * S, top_row2 * S], fill=LINE, width=2 * S)
    cx = xs[1] + 120
    d.line([cx * S, bus_y * S, cx * S, boxes["case"][3] * S], fill=LINE, width=2 * S)
    d.polygon([(cx * S, boxes["case"][3] * S), ((cx - 6) * S, (boxes["case"][3] + 10) * S),
               ((cx + 6) * S, (boxes["case"][3] + 10) * S)], fill=LINE)
    lab = "every dossier entry: case_id → promotion_case (ON DELETE CASCADE)"
    w = d.textlength(lab, font=LBL) / S
    d.text(((cx - 10 - w) * S, (bus_y - 20) * S), lab, font=LBL, fill=INK)

    bottom = max(b[3] for b in boxes.values()) + 30
    img = img.crop((0, 0, 1720 * S, int(bottom * S)))
    out = ROOT / "docs" / "er_overview.png"
    img.save(out)
    print("wrote", out, img.size)


if __name__ == "__main__":
    main()
