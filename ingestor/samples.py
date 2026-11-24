"""Generate the bundled Lakeside Auto Group (sample) legacy files.

The files are fictional. They exist so the demo can run offline: a crooked
scan, a mainframe extract, a messy spreadsheet, and a plain memo.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import numpy as np
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .copybook import encode_file, encode_record, load_copybook, parse_copybook
from .paths import SAMPLES_DIR

# ---------------------------------------------------------------------------
# Shared fictional facts (imported by tests)
# ---------------------------------------------------------------------------

COMPANY = "Lakeside Auto Group (sample)"

# Check digits are real ISO 3779 values. The vehicles and people are not.
VIN_ANITA_ACCORD = "1HGCV2F36KA123456"       # 2019 Honda Accord
VIN_MARCUS_CIVIC = "19XFC2F58JE123456"       # 2018 Honda Civic
VIN_DENISE_RAV4 = "2T3P8RFV6RW223456"        # 2024 Toyota RAV4
VIN_THOMAS_CRV = "5J6RW2H86PA123456"         # 2023 Honda CR-V
VIN_CARLA_CAMRY = "4T1C11AK8LU123456"        # 2020 Toyota Camry
VIN_JAMES_PILOT = "5FNYF6H90MB123456"        # 2021 Honda Pilot
VIN_HELEN_HIGHLANDER = "5TDGZRBH9NS123456"   # 2022 Toyota Highlander
VIN_DAVID_ODYSSEY = "5FNRL5H69GB123456"      # 2016 Honda Odyssey

RO_MARCUS = "RO-184422"
DEAL_DENISE = "D-44821"
CLAIM_ANITA = "WTY-26-04418"
RECALL_CAMPAIGN = "24V-312"
WARRANTY_TOTAL = Decimal("1847.22")
MARCUS_RO_TOTAL = Decimal("487.62")
DENISE_FRONT_GROSS = Decimal("2150.00")

FONT_DIR = Path("/usr/share/fonts/truetype/sand-box/google")
COURIER = FONT_DIR / "Courier Prime" / "CourierPrime-Regular.ttf"
COURIER_BOLD = FONT_DIR / "Courier Prime" / "CourierPrime-Bold.ttf"
SERIF = FONT_DIR / "IBM Plex Serif" / "IBMPlexSerif-Regular.ttf"
SERIF_BOLD = FONT_DIR / "IBM Plex Serif" / "IBMPlexSerif-Bold.ttf"

# Letter at 200 dpi.
PAGE_W, PAGE_H = 1700, 2200
PAPER = (236, 226, 198)
INK = (28, 24, 18)
RULE = (90, 70, 50)
FAINT = (170, 150, 120)


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    if path.is_file():
        return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _new_page(color: tuple[int, int, int] = PAPER) -> Image.Image:
    return Image.new("RGB", (PAGE_W, PAGE_H), color)


def age_scan(
    image: Image.Image,
    seed: int,
    skew: float = 1.3,
    noise: float = 7.0,
) -> Image.Image:
    """Rotate, grain, and slightly fade a clean form so OCR has real work to do."""
    rng = np.random.default_rng(seed)
    paper = PAPER
    # expand=False keeps letter size and a margin around the header,
    # so a small skew does not crop the store name off the page.
    rotated = image.rotate(
        skew,
        resample=Image.Resampling.BICUBIC,
        expand=False,
        fillcolor=paper,
    )
    arr = np.asarray(rotated).astype(np.int16)
    grain = rng.normal(0, noise, arr.shape).astype(np.int16)
    arr = np.clip(arr + grain, 0, 255)
    # A mild brightness gradient, like a scanner that was a little uneven.
    yy = np.linspace(-1, 1, arr.shape[0])[:, None]
    xx = np.linspace(-1, 1, arr.shape[1])[None, :]
    vignette = (1 - 0.08 * (xx**2 + yy**2))[:, :, None]
    arr = np.clip(arr * vignette, 0, 255).astype(np.uint8)
    out = Image.fromarray(arr, mode="RGB")
    # A faint coffee ring in the margin, away from the values we need to read.
    overlay = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ring = ImageDraw.Draw(overlay)
    ring.ellipse((120, 1680, 420, 1980), outline=(140, 90, 50, 45), width=18)
    ring.ellipse((132, 1692, 408, 1968), outline=(140, 90, 50, 25), width=8)
    out = Image.alpha_composite(out.convert("RGBA"), overlay).convert("RGB")
    return out.filter(ImageFilter.GaussianBlur(radius=0.4))


def _draw_line(draw: ImageDraw.ImageDraw, x1, y1, x2, y2, width=2, fill=RULE):
    draw.line((x1, y1, x2, y2), fill=fill, width=width)


def _box(draw: ImageDraw.ImageDraw, xy, width=2, fill=None):
    draw.rectangle(xy, outline=RULE, width=width, fill=fill)


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------


def render_repair_order() -> Image.Image:
    img = _new_page()
    d = ImageDraw.Draw(img)
    title = _font(SERIF_BOLD, 44)
    head = _font(SERIF, 22)
    label = _font(COURIER_BOLD, 28)
    body = _font(COURIER, 28)
    small = _font(COURIER, 22)

    d.text((80, 70), "LAKESIDE HONDA", font=title, fill=INK)
    d.text((80, 130), "A store of Lakeside Auto Group", font=head, fill=INK)
    d.text((80, 168), "123 Lakeside Drive  ·  Service Department", font=head, fill=INK)
    d.text((1180, 70), "REPAIR ORDER", font=title, fill=INK)
    _draw_line(d, 80, 220, 1620, 220, width=3)

    def field(x, y, lab, val, vwidth=700):
        d.text((x, y), lab, font=label, fill=INK)
        lx = x + d.textlength(lab, font=label) + 16
        d.text((lx, y), val, font=body, fill=INK)
        _draw_line(d, lx, y + 36, lx + vwidth, y + 36, width=1, fill=FAINT)

    field(80, 260, "RO NO.", RO_MARCUS, 420)
    field(900, 260, "DATE", "11/03/2026", 420)
    field(80, 330, "CUSTOMER", "MARCUS WEBB", 700)
    field(900, 330, "PHONE", "(555) 014-2281", 420)
    field(80, 400, "YEAR/MAKE/MODEL", "2018 HONDA CIVIC", 700)
    field(80, 470, "VIN", VIN_MARCUS_CIVIC, 700)
    field(900, 470, "MILEAGE", "84210", 420)
    field(80, 540, "ADVISOR", "MAYA CHEN", 700)
    field(900, 540, "STATUS", "CLOSED", 420)

    _box(d, (80, 630, 1620, 1480))
    headers = [(100, "OP"), (220, "DESCRIPTION"), (1100, "HOURS"), (1320, "AMOUNT")]
    for x, h in headers:
        d.text((x, 650), h, font=label, fill=INK)
    _draw_line(d, 80, 700, 1620, 700, width=2)

    rows = [
        ("41", "VALVE COVER GASKET / OIL LEAK", "2.4", "312.00"),
        ("", "PARTS - GASKET SET", "", "129.40"),
        ("", "SHOP SUPPLIES", "", "16.22"),
        ("", "TAX AND ENVIRONMENTAL", "", "30.00"),
    ]
    y = 730
    for op, desc, hours, amt in rows:
        d.text((100, y), op, font=body, fill=INK)
        d.text((220, y), desc, font=body, fill=INK)
        d.text((1100, y), hours, font=body, fill=INK)
        d.text((1320, y), amt, font=body, fill=INK)
        y += 70

    _draw_line(d, 1260, 1100, 1580, 1100, width=2)
    d.text((1100, 1130), "TOTAL", font=label, fill=INK)
    d.text((1320, 1130), f"${MARCUS_RO_TOTAL}", font=label, fill=INK)

    d.text((100, 1280), "COMPLAINT: CUSTOMER REPORTS OIL ON THE DRIVEWAY", font=body, fill=INK)
    d.text((100, 1350), "CAUSE: VALVE COVER GASKET SEEPING", font=body, fill=INK)
    d.text((100, 1420), "CORRECTION: REPLACED GASKET, CLEANED, RECHECKED", font=body, fill=INK)

    d.text((80, 1560), "CUSTOMER SIGNATURE: ___________________________", font=body, fill=INK)
    d.text((900, 1560), "DATE: 11/03/2026", font=body, fill=INK)
    d.text((80, 2040), "Sample document for a portfolio demo. Not a real repair order.", font=small, fill=RULE)
    return img


def render_deal_recap() -> Image.Image:
    img = _new_page((232, 224, 208))
    d = ImageDraw.Draw(img)
    title = _font(SERIF_BOLD, 42)
    head = _font(SERIF, 22)
    label = _font(COURIER_BOLD, 28)
    body = _font(COURIER, 28)
    small = _font(COURIER, 22)

    d.text((80, 70), "LAKESIDE TOYOTA", font=title, fill=INK)
    d.text((80, 130), "A store of Lakeside Auto Group  ·  F&I Deal Recap", font=head, fill=INK)
    d.text((1180, 70), "DEAL RECAP", font=title, fill=INK)
    d.text((1180, 130), f"DEAL {DEAL_DENISE}", font=label, fill=INK)
    _draw_line(d, 80, 220, 1620, 220, width=3)

    def row(y, lab, val, x=80):
        d.text((x, y), lab, font=label, fill=INK)
        d.text((x + 420, y), val, font=body, fill=INK)

    row(260, "CUSTOMER", "DENISE PATEL")
    row(260, "DATE", "10/16/2026", x=900)
    row(330, "YEAR/MAKE/MODEL", "2024 TOYOTA RAV4 XLE")
    row(400, "VIN", VIN_DENISE_RAV4)
    row(470, "STOCK NO.", "T-4419")
    row(470, "F&I MANAGER", "CHRIS ALVAREZ", x=900)
    row(540, "SALESPERSON", "ELENA VASQUEZ")
    row(540, "TERM / APR", "60 MO  /  6.49%", x=900)

    _box(d, (80, 630, 1620, 1500))
    d.text((100, 660), "FRONT / BACK / PRODUCTS", font=label, fill=INK)
    _draw_line(d, 80, 710, 1620, 710, width=2)

    lines = [
        ("SELLING PRICE", "$34,980.00"),
        ("TRADE ALLOWANCE (2017 CAMRY)", "$8,500.00"),
        ("PAYOFF", "$6,120.00"),
        ("FRONT GROSS", "$2,150.00"),
        ("VSC (TOYOTA CARE PLUS)", "$1,895.00"),
        ("GAP", "$795.00"),
        ("BACK GROSS", "$1,420.00"),
        ("PACK", "$350.00"),
        ("RESERVE", "$640.00"),
        ("TOTAL GROSS", "$3,570.00"),
    ]
    y = 740
    for lab, val in lines:
        d.text((120, y), lab, font=body, fill=INK)
        d.text((1200, y), val, font=body, fill=INK)
        y += 62

    d.text((100, 1600), "NOTES: CUSTOMER TOOK VSC AND GAP. DEAL FUNDED 10/18/2026.", font=body, fill=INK)
    d.text((100, 1680), "DESK COPY — PLACE IN THE DEAL JACKET BEHIND THE BUYER'S ORDER.", font=body, fill=INK)
    d.text((80, 2040), "Sample document for a portfolio demo. Not a real deal recap.", font=small, fill=RULE)
    return img


def render_warranty_claim() -> Image.Image:
    img = _new_page((240, 228, 200))
    d = ImageDraw.Draw(img)
    title = _font(SERIF_BOLD, 40)
    head = _font(SERIF, 22)
    label = _font(COURIER_BOLD, 28)
    body = _font(COURIER, 28)
    small = _font(COURIER, 22)

    d.text((80, 70), "LAKESIDE HONDA", font=title, fill=INK)
    d.text((80, 130), "Warranty claim  ·  Lakeside Auto Group", font=head, fill=INK)
    d.text((1100, 70), "WARRANTY CLAIM", font=title, fill=INK)
    d.text((1100, 130), f"CLAIM {CLAIM_ANITA}", font=label, fill=INK)
    _draw_line(d, 80, 220, 1620, 220, width=3)

    def field(y, lab, val, x=80):
        d.text((x, y), lab, font=label, fill=INK)
        d.text((x + 400, y), val, font=body, fill=INK)

    field(260, "CUSTOMER", "ANITA ROSALES")
    field(260, "DATE", "03/18/2026", x=900)
    field(330, "YEAR/MAKE/MODEL", "2019 HONDA ACCORD")
    field(400, "VIN", VIN_ANITA_ACCORD)
    field(470, "MILEAGE", "67440")
    field(470, "RO NO.", "RO-190118", x=900)
    field(540, "ADVISOR", "MAYA CHEN")
    field(540, "AUTH CODE", "HND-66219", x=900)

    _box(d, (80, 630, 1620, 1500))
    d.text((100, 660), "LABOR AND PARTS", font=label, fill=INK)
    _draw_line(d, 80, 710, 1620, 710, width=2)
    d.text((100, 740), "OP    DESCRIPTION                          LABOR         PARTS", font=label, fill=INK)

    lines = [
        "41    TRANSMISSION COOLER LINE             2.8  $420.00",
        "      HOSE AND CLAMPS                                    $1,085.22",
        "      FLUID                                              $150.00",
        "      DIAGNOSTIC TIME                     1.2  $192.00",
    ]
    y = 810
    for line in lines:
        d.text((100, y), line, font=body, fill=INK)
        y += 70

    _draw_line(d, 1100, 1180, 1580, 1180, width=2)
    d.text((100, 1220), "LABOR TOTAL                         $612.00", font=body, fill=INK)
    d.text((100, 1290), "PARTS TOTAL                         $1,235.22", font=body, fill=INK)
    d.text((100, 1370), "CLAIM TOTAL                         $1,847.22", font=label, fill=INK)

    d.text((100, 1580), "FAILURE: TRANSMISSION COOLER LINE LEAKING AT THE CRIMP.", font=body, fill=INK)
    d.text((100, 1650), "CAUSE: CORROSION AT THE FACTORY CRIMP. COVERED UNDER POWERTRAIN.", font=body, fill=INK)
    d.text((100, 1720), "SUBMITTED TO AMERICAN HONDA 03/18/2026.  AUTHORIZED SAME DAY.", font=body, fill=INK)
    d.text((80, 2040), "Sample document for a portfolio demo. Not a real warranty claim.", font=small, fill=RULE)
    return img


def _save_form(image: Image.Image, stem: str, seed: int, skew: float, folder: Path | None = None) -> dict[str, Path]:
    folder = Path(folder) if folder is not None else (SAMPLES_DIR / "forms")
    folder.mkdir(parents=True, exist_ok=True)
    aged = age_scan(image, seed=seed, skew=skew)
    # JPEG is how a real scan usually lands, and it keeps the repo small.
    jpg = folder / f"{stem}.jpg"
    pdf = folder / f"{stem}.pdf"
    aged.convert("RGB").save(jpg, "JPEG", quality=90, optimize=True, dpi=(200, 200))
    aged.convert("RGB").save(pdf, "PDF", resolution=200.0)
    return {"jpg": jpg, "pdf": pdf}


# ---------------------------------------------------------------------------
# Mainframe
# ---------------------------------------------------------------------------

COPYBOOK_SOURCE = """\
      *****************************************************************
      * LAKESIDE AUTO GROUP (SAMPLE) -- LEGACY DMS DEAL EXTRACT
      * FIXED-LENGTH CUSTOMER / DEAL RECORD FROM THE MAINFRAME.
      * THIS FILE IS FICTIONAL DEMO DATA, NOT A REAL CUSTOMER FILE.
      *****************************************************************
       01  DEAL-RECORD.
           05  CUST-ID          PIC 9(8).
           05  CUST-NAME        PIC X(30).
           05  CUST-STATUS      PIC X.
           05  CUST-TYPE        REDEFINES CUST-STATUS PIC X.
           05  STORE-ID         PIC X(4).
           05  VIN              PIC X(17).
           05  DEAL-DATE        PIC 9(8).
           05  GROSS-AMT        PIC S9(9)V99 COMP-3.
           05  NET-AMT          PIC S9(7)V99 COMP-3.
           05  VEHICLE-COUNT    PIC 9(2).
           05  VEHICLE-INFO     OCCURS 2 TIMES.
               10  VEH-YEAR     PIC 9(4).
               10  VEH-MAKE     PIC X(12).
           05  FILLER           PIC X(5).
"""

# Eight good records. A ninth is written with a corrupted COMP-3 field, and
# a short leftover chunk is appended so the quality report has rejects.
MAINFRAME_ROWS = [
    {
        "CUST_ID": 18401,
        "CUST_NAME": "ROSALES, ANITA M",
        "CUST_STATUS": "A",
        "STORE_ID": "HOND",
        "VIN": VIN_ANITA_ACCORD,
        "DEAL_DATE": 20190322,
        "GROSS_AMT": Decimal("28450.00"),
        "NET_AMT": Decimal("26100.00"),
        "VEHICLE_COUNT": 2,
        "VEHICLE_INFO": [
            {"VEH_YEAR": 2019, "VEH_MAKE": "HONDA"},
            {"VEH_YEAR": 2014, "VEH_MAKE": "HONDA"},
        ],
    },
    {
        "CUST_ID": 18402,
        "CUST_NAME": "WEBB, MARCUS",
        "CUST_STATUS": "A",
        "STORE_ID": "HOND",
        "VIN": VIN_MARCUS_CIVIC,
        "DEAL_DATE": 20180614,
        "GROSS_AMT": Decimal("19820.00"),
        "NET_AMT": Decimal("18240.50"),
        "VEHICLE_COUNT": 1,
        "VEHICLE_INFO": [
            {"VEH_YEAR": 2018, "VEH_MAKE": "HONDA"},
            {"VEH_YEAR": 0, "VEH_MAKE": ""},
        ],
    },
    {
        "CUST_ID": 18403,
        "CUST_NAME": "PATEL, DENISE",
        "CUST_STATUS": "A",
        "STORE_ID": "TOYT",
        "VIN": VIN_DENISE_RAV4,
        "DEAL_DATE": 20261016,
        "GROSS_AMT": Decimal("34980.00"),
        "NET_AMT": Decimal("31210.00"),
        "VEHICLE_COUNT": 2,
        "VEHICLE_INFO": [
            {"VEH_YEAR": 2024, "VEH_MAKE": "TOYOTA"},
            {"VEH_YEAR": 2017, "VEH_MAKE": "TOYOTA"},
        ],
    },
    {
        "CUST_ID": 18404,
        "CUST_NAME": "NGUYEN, THOMAS",
        "CUST_STATUS": "A",
        "STORE_ID": "HOND",
        "VIN": VIN_THOMAS_CRV,
        "DEAL_DATE": 20230402,
        "GROSS_AMT": Decimal("32750.00"),
        "NET_AMT": Decimal("30115.25"),
        "VEHICLE_COUNT": 1,
        "VEHICLE_INFO": [
            {"VEH_YEAR": 2023, "VEH_MAKE": "HONDA"},
            {"VEH_YEAR": 0, "VEH_MAKE": ""},
        ],
    },
    {
        "CUST_ID": 18405,
        "CUST_NAME": "BISHOP, CARLA",
        "CUST_STATUS": "A",
        "STORE_ID": "TOYT",
        "VIN": VIN_CARLA_CAMRY,
        "DEAL_DATE": 20201119,
        "GROSS_AMT": Decimal("24100.00"),
        "NET_AMT": Decimal("22380.00"),
        "VEHICLE_COUNT": 1,
        "VEHICLE_INFO": [
            {"VEH_YEAR": 2020, "VEH_MAKE": "TOYOTA"},
            {"VEH_YEAR": 0, "VEH_MAKE": ""},
        ],
    },
    {
        "CUST_ID": 18406,
        "CUST_NAME": "OKONKWO, JAMES",
        "CUST_STATUS": "A",
        "STORE_ID": "HOND",
        "VIN": VIN_JAMES_PILOT,
        "DEAL_DATE": 20210508,
        "GROSS_AMT": Decimal("41200.00"),
        "NET_AMT": Decimal("38540.00"),
        "VEHICLE_COUNT": 1,
        "VEHICLE_INFO": [
            {"VEH_YEAR": 2021, "VEH_MAKE": "HONDA"},
            {"VEH_YEAR": 0, "VEH_MAKE": ""},
        ],
    },
    {
        "CUST_ID": 18407,
        "CUST_NAME": "PARK, HELEN",
        "CUST_STATUS": "A",
        "STORE_ID": "TOYT",
        "VIN": VIN_HELEN_HIGHLANDER,
        "DEAL_DATE": 20220821,
        "GROSS_AMT": Decimal("44890.00"),
        "NET_AMT": Decimal("41920.75"),
        "VEHICLE_COUNT": 1,
        "VEHICLE_INFO": [
            {"VEH_YEAR": 2022, "VEH_MAKE": "TOYOTA"},
            {"VEH_YEAR": 0, "VEH_MAKE": ""},
        ],
    },
    {
        "CUST_ID": 18408,
        "CUST_NAME": "RUIZ, DAVID",
        "CUST_STATUS": "C",
        "STORE_ID": "HOND",
        "VIN": VIN_DAVID_ODYSSEY,
        "DEAL_DATE": 20160729,
        "GROSS_AMT": Decimal("0.00"),
        "NET_AMT": Decimal("-125.00"),
        "VEHICLE_COUNT": 1,
        "VEHICLE_INFO": [
            {"VEH_YEAR": 2016, "VEH_MAKE": "HONDA"},
            {"VEH_YEAR": 0, "VEH_MAKE": ""},
        ],
    },
]


def write_mainframe(folder: Path | None = None) -> dict[str, Path]:
    folder = folder or (SAMPLES_DIR / "mainframe")
    folder.mkdir(parents=True, exist_ok=True)
    cpy = folder / "CUSTDEAL.CPY"
    dat = folder / "CUSTDEAL.DAT"
    cpy.write_text(COPYBOOK_SOURCE, encoding="utf-8")
    book = parse_copybook(COPYBOOK_SOURCE)
    good = encode_file(book, MAINFRAME_ROWS)
    # Record 9: a copy of Anita's row with a smashed packed-decimal nibble.
    smashed = bytearray(encode_record(book, MAINFRAME_ROWS[0]))
    # CUST_ID 18409 so it is visibly a different row in a hex dump.
    smashed[0:8] = f"{18409:08d}".encode("cp037")
    gross = next(f for f in book.fields() if f.name == "GROSS_AMT")
    smashed[gross.offset + 2] = 0xAA
    # Record 10: a truncated leftover from a bad extract job.
    leftover = b"\x00\xF1\xF8\x40" + "BROKEN".encode("cp037")
    dat.write_bytes(good + bytes(smashed) + leftover)
    return {"cpy": cpy, "dat": dat}


# ---------------------------------------------------------------------------
# Messy CSV and Excel
# ---------------------------------------------------------------------------

CSV_TEXT = """\
Lakeside Auto Group — Service History Export (unofficial pull 11/24/2026)
Store, dates, and amounts are not normalized. Do not use for month-end.

Cust. Name,DATE,Vin #,RO Amt,Advisor,RO #,Store,Year,Make,Model
"WEBB, MARCUS",11/3/26,19XFC2F58JE123456,"$487.62",Maya Chen,RO-184422,Lakeside Honda,2018,Honda,Civic
"ROSALES, ANITA M",18-Mar-2026,1HG CV2F36 KA123456,1847.22,Maya Chen,RO-190118,Lakeside Honda,2019,Honda,Accord
"Nguyen, Thomas",2026-09-14,5J6RW2H86PA123456,"1,102.00",Jose Ramirez,RO-191002,Lakeside Honda,2023,Honda,CR-V
"BISHOP, CARLA",11/02/26,4T1C11AK8LU123456,($88.40),Priya Shah,RO-77410,Lakeside Toyota,2020,Toyota,Camry
"OKONKWO, JAMES",20260930,5FNYF6H90MB123456,256.00,Maya Chen,RO-191440,Lakeside Honda,2021,Honda,Pilot
"PARK, HELEN",Oct 4 2026,5TDGZRBH9NS123456,980.15,Priya Shah,RO-77502,Lakeside Toyota,2022,Toyota,Highlander
"RUIZ, DAVID",07/29/16,5FNRL5H69GB123456,125.00-,Jose Ramirez,RO-1120,Lakeside Honda,2016,Honda,Odyssey
"WEBB, MARCUS",not-a-date,19XFC2F5,see jacket,Maya Chen,RO-184500,Lakeside Honda,2018,Honda,Civic
,,,,,,
"""


def write_csv(folder: Path | None = None) -> Path:
    folder = folder or (SAMPLES_DIR / "exports")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "service-history-export.csv"
    path.write_text(CSV_TEXT, encoding="utf-8")
    return path


def write_excel(folder: Path | None = None) -> Path:
    folder = folder or (SAMPLES_DIR / "exports")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "deal-register-export.xlsx"
    book = Workbook()
    sheet = book.active
    sheet.title = "Deal Register"
    sheet["A1"] = "Deal Register Export - Lakeside Auto Group - pulled 11/24/2026  (unofficial)"
    sheet["A1"].font = Font(bold=True, size=14)
    sheet.merge_cells("A1:H1")
    # Row 2 is intentionally blank.
    headers = [
        " Customer Name ",
        "Deal Date",
        "Vin #",
        " Front Gross$ ",
        "Back Gross",
        "Deal #",
        "Store",
        "FI Manager",
    ]
    for col, header in enumerate(headers, start=1):
        cell = sheet.cell(3, col, header)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")

    # Mix of Excel serials, ISO, US slashes, and MON-YYYY text.
    # 2026-10-16 Excel serial:
    from datetime import date, timedelta

    def serial(y, m, d):
        return (date(y, m, d) - date(1899, 12, 30)).days

    rows = [
        ("PATEL, DENISE", serial(2026, 10, 16), VIN_DENISE_RAV4, 2150.00, 1420.00, DEAL_DENISE, "Lakeside Toyota", "CHRIS ALVAREZ"),
        ("ROSALES, ANITA M", "03/22/2019", VIN_ANITA_ACCORD, "2,850.00", 940.00, "D-11880", "Lakeside Honda", "Chris Alvarez"),
        ("NGUYEN, THOMAS", "2023-04-02", VIN_THOMAS_CRV, 1950, 880, "D-33102", "Lakeside Honda", "sofia lane"),
        ("PARK, HELEN", "21-AUG-2022", VIN_HELEN_HIGHLANDER, "$2,400.00", 1100, "D-39011", "Lakeside Toyota", "CHRIS ALVAREZ"),
        ("OKONKWO, JAMES", serial(2021, 5, 8), VIN_JAMES_PILOT, 2200, "(125.00)", "D-27440", "Lakeside Honda", "Sofia Lane"),
        ("????", "tomorrow", "N/A", "TBD", "", "", "Lakeside Honda", ""),
    ]
    for r, row in enumerate(rows, start=4):
        for c, value in enumerate(row, start=1):
            sheet.cell(r, c, value)
    book.save(path)
    return path


# ---------------------------------------------------------------------------
# Memo
# ---------------------------------------------------------------------------

MEMO_TEXT = f"""\
LAKESIDE AUTO GROUP
Lakeside Honda — General Manager

MEMO

To:      Service and F&I Managers, Lakeside Honda
From:    Patricia Walsh — General Manager
Date:    November 12, 2026
Subject: Fuel pump recall {RECALL_CAMPAIGN} — pull the paper jackets

We received the Honda campaign list for recall {RECALL_CAMPAIGN} (fuel pump) this morning. Please pull the deal jackets and any open repair orders for affected vehicles still in our service history.

One I already recognize is Anita Rosales, 2019 Honda Accord, VIN {VIN_ANITA_ACCORD}. She was in on March 18, 2026 for a warranty claim on a transmission cooler line (claim {CLAIM_ANITA}). That jacket is still in the file room, not in the DMS.

If a customer on the campaign list only exists on a paper RO or a mainframe extract, do not wait for the new system. Flag the VIN, call the customer, and log the contact on the recall tracker.

This is a sample memo for a portfolio demo. Lakeside Auto Group is fictional.

Patricia Walsh
General Manager, Lakeside Honda
"""


def write_memo(folder: Path | None = None) -> Path:
    folder = folder or (SAMPLES_DIR / "memos")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "gm-recall-memo.txt"
    path.write_text(MEMO_TEXT, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_all(root: Path | None = None) -> dict[str, Path]:
    """Write every bundled sample and return a name-to-path map."""
    base = Path(root) if root is not None else SAMPLES_DIR
    base.mkdir(parents=True, exist_ok=True)
    mf = write_mainframe(base / "mainframe")
    csv_path = write_csv(base / "exports")
    xlsx_path = write_excel(base / "exports")
    memo_path = write_memo(base / "memos")
    repair = _save_form(render_repair_order(), "repair-order-lakeside-honda", seed=11, skew=1.4, folder=base / "forms")
    recap = _save_form(render_deal_recap(), "deal-recap-lakeside-toyota", seed=22, skew=-1.1, folder=base / "forms")
    warranty = _save_form(render_warranty_claim(), "warranty-claim-lakeside-honda", seed=33, skew=1.7, folder=base / "forms")

    return {
        "copybook": mf["cpy"],
        "mainframe": mf["dat"],
        "csv": csv_path,
        "excel": xlsx_path,
        "memo": memo_path,
        "repair_order": repair["jpg"],
        "repair_order_pdf": repair["pdf"],
        "deal_recap": recap["jpg"],
        "deal_recap_pdf": recap["pdf"],
        "warranty_claim": warranty["jpg"],
        "warranty_claim_pdf": warranty["pdf"],
    }


if __name__ == "__main__":
    written = generate_all()
    for name, path in written.items():
        print(f"{name}: {path}")
