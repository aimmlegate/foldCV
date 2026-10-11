"""Render a sourced resume payload in the fixed reference layout."""

import argparse
import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Flowable, Paragraph, Spacer

from check_archive import check
from policy import FOCUS, key

ASSETS = Path(__file__).resolve().parents[1] / "assets"
ICON_ALIASES = json.loads((ASSETS / "icon-aliases.json").read_text())
PAGE_W, PAGE_H = 596, 842
BOTTOM = 770


def setup_fonts():
    for weight in ("Light", "Regular", "Semibold", "Bold", "Black"):
        pdfmetrics.registerFont(TTFont(weight, str(ASSETS / "fonts" / f"SourceSansPro-{weight}.ttf")))


def paragraph(text, *, font="Light", size=10, leading=12.57, after=0, keep=False, bullet=False):
    supported = pdfmetrics.getFont(font).face.charToGlyph
    missing = {c for c in text if not c.isspace() and ord(c) not in supported}
    if missing:
        raise ValueError(f"Font {font} cannot render: {sorted(missing)}")
    style = ParagraphStyle("resume", fontName=font, fontSize=size, leading=leading,
                           spaceAfter=after, keepWithNext=keep, allowWidows=0, allowOrphans=0,
                           embeddedHyphenation=1,
                           leftIndent=36 if bullet else 0, bulletIndent=18,
                           bulletFontName="Helvetica", bulletFontSize=14)
    return Paragraph(escape(text).replace("\n", "<br/>"), style, bulletText="•" if bullet else None)


def attached_space(height):
    space = Spacer(1, height)
    space.keepWithNext = True
    return space


class Section(Flowable):
    def __init__(self, title, bar=False):
        super().__init__()
        self.title, self.bar = title, bar
        self.height = 28 if bar else 19
        self.keepWithNext = True

    def wrap(self, width, height):
        self.width = width
        return width, self.height

    def draw(self):
        c = self.canv
        if self.bar:
            c.setFillColorRGB(.9373, .9373, .9373)
            c.rect(-10, 0, self.width + 25, self.height, stroke=0, fill=1)
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Bold", 14)
        c.drawString(-5 if self.bar else 0, self.height - 15, self.title)


class Focus(Flowable):
    def __init__(self, item):
        super().__init__()
        self.item = item
        self.icon_path = None
        if item["icon"]:
            self.icon_path = ASSETS / "images" / f"{item['icon']}.png"
        else:
            alias = FOCUS.get(key(item["label"]["text"])) or ICON_ALIASES.get(item["label"]["text"].strip().casefold())
            if alias:
                self.icon_path = next((ASSETS / folder / f"{alias}.png" for folder in ("images", "devicon")
                                       if (ASSETS / folder / f"{alias}.png").exists()), None)
        self.label = paragraph(item["label"]["text"], font="Semibold")
        self.duration = paragraph(item["duration"]["text"]) if item["duration"] else None

    def wrap(self, width, height):
        self.width = width
        self.label_h = self.label.wrap(width - 37, height)[1]
        self.duration_h = self.duration.wrap(width - 37, height)[1] if self.duration else 0
        self.height = max(38, self.label_h + self.duration_h + 7)
        return width, self.height

    def draw(self):
        if self.icon_path:
            self.canv.drawImage(str(self.icon_path),
                                4.5, self.height - 32, 28, 32,
                                preserveAspectRatio=True, anchor="c", mask="auto")
        self.label.drawOn(self.canv, 37, self.height - self.label_h)
        if self.duration:
            self.duration.drawOn(self.canv, 37, self.height - self.label_h - self.duration_h)


def paginate(items, width):
    pages, placed, top = [], [], 95
    pending = list(items)

    def new_page():
        nonlocal placed, top
        pages.append(placed)
        placed, top = [], 24

    while pending:
        item = pending[0]
        if not placed and isinstance(item, Spacer):
            pending.pop(0)
            continue
        before, after = item.getSpaceBefore(), item.getSpaceAfter()
        available = BOTTOM - top - before
        _, height = item.wrap(width, available)
        # Keep a heading with the first content that follows it.
        if item.getKeepWithNext():
            group_h = 0
            for following in pending:
                group_h += following.getSpaceBefore() + following.wrap(width, BOTTOM)[1] + following.getSpaceAfter()
                if not following.getKeepWithNext():
                    break
            if placed and group_h > BOTTOM - top:
                new_page()
                continue
        if height <= available:
            placed.append((item, top + before, height))
            top += before + height + after
            pending.pop(0)
            continue
        parts = item.split(width, available)
        if parts:
            pending[:1] = parts
            continue
        if not placed:
            raise ValueError(f"An element cannot fit in the column: {type(item).__name__}")
        new_page()
    if placed:
        pages.append(placed)
    return pages


def build_columns(data):
    side = []
    if data["focus"]:
        side.append(Section("ФОКУС"))
        if data.get("schema_version") in (2, "2"):
            side.append(paragraph("Оценка по периодам проектов", size=8, leading=10, after=8, keep=True))
        side.extend(Focus(item) for item in data["focus"])
        side.append(Spacer(1, 8))
    for section in data["sidebar"]:
        if not section["items"]:
            continue
        side.append(Section(section["title"]))
        side.extend(paragraph(item["text"], after=8) for item in section["items"])
        side.append(Spacer(1, 6))

    main = [Section("О СЕБЕ"), paragraph(data["candidate"]["summary"]["text"], after=10)]
    if data["projects"]:
        main.extend([Section("ПРОЕКТЫ", bar=True), attached_space(14)])
    for project in data["projects"]:
        main.append(paragraph(project["company"]["text"], font="Semibold", size=12, leading=15.08, keep=True))
        main.append(paragraph(project["period"]["text"], font="Regular", keep=True))
        if project["stack"]:
            main.append(paragraph(project["stack"]["text"], font="Regular", keep=True))
        if project["description"]:
            main.append(paragraph(project["description"]["text"], keep=True))
        main.append(paragraph("Роль: " + project["role"]["text"], keep=bool(project["tasks"] or project["results"])))
        for label, key in (("Задачи:", "tasks"), ("Личные результаты:", "results")):
            if project[key]:
                main.append(paragraph(label, keep=True))
                main.extend(paragraph(item["text"], bullet=True) for item in project[key])
        main.append(Spacer(1, 12.57))
    if data.get("earlier_experience"):
        main.extend([Section("РАННИЙ ОПЫТ", bar=True), attached_space(8)])
        main.extend(paragraph(item["summary"]["text"], after=12.57) for item in data["earlier_experience"])
    tail_start = len(main)
    if data["achievements"]:
        main.append(paragraph("Ключевые достижения:", font="Semibold", keep=True))
        main.extend(paragraph(item["text"], bullet=True) for item in data["achievements"])
        main.append(Spacer(1, 12.57))
    for group in data["skill_groups"]:
        main.extend([Section(group["title"], bar=True), attached_space(5),
                     paragraph(group["items"]["text"], after=8)])
    # Avoid a nearly empty last page containing only one or two skill lists.
    tail = main[tail_start:]
    tail_height = sum(f.wrap(420, BOTTOM)[1] + f.getSpaceBefore() + f.getSpaceAfter() for f in tail)
    if tail_height <= BOTTOM - 24:
        for flowable in tail[:-1]:
            flowable.keepWithNext = True
    return paginate(side, 118), paginate(main, 420)


def draw_header(canvas, candidate):
    for field, font, size, top, max_height in (("name", "Black", 18, 14, 24),
                                              ("title", "Semibold", 16, 40, 34)):
        p = paragraph(candidate[field]["text"], font=font, size=size, leading=size * 1.15)
        _, h = p.wrap(450, max_height)
        if h > max_height:
            raise ValueError(f"Header {field} is too long; shorten the display label")
        p.drawOn(canvas, 21.26, PAGE_H - top - h)
    canvas.drawImage(str(ASSETS / "images" / "foldcv.png"), 487.6, PAGE_H - 56.1,
                     104.9, 37.4, preserveAspectRatio=True, mask="auto")
    canvas.setStrokeColorRGB(.5333, .5333, .5333)
    canvas.setLineWidth(.6)
    canvas.line(10, PAGE_H - 79.5, 535, PAGE_H - 79.5)


def render(data, target):
    setup_fonts()
    side, main = build_columns(data)
    target.parent.mkdir(parents=True, exist_ok=True)
    c = Canvas(str(target), pagesize=(PAGE_W, PAGE_H), pageCompression=1, invariant=1)
    c.setTitle(data["candidate"]["name"]["text"] + " — CV")
    c.setAuthor("")
    c.setCreator("Resume formatter")
    count = max(len(side), len(main))
    for page in range(count):
        if page == 0:
            draw_header(c, data["candidate"])
        for column, x, width in ((side, 26.5, 118), (main, 160.76, 420)):
            if page < len(column):
                for flowable, top, height in column[page]:
                    flowable.wrap(width, height)
                    flowable.drawOn(c, x, PAGE_H - top - height)
        c.setFont("Light", 12)
        c.setFillColorRGB(0, 0, 0)
        c.drawCentredString(275.65, 42, "mail@example.com")
        c.showPage()
    c.save()
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payload", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.payload.read_text())
    source = json.loads(args.source.read_text())
    check(payload, json.loads(args.archive.read_text()), args.archive, source)
    print(f"Rendered {render(payload, args.output)} pages to {args.output}")


if __name__ == "__main__":
    main()
