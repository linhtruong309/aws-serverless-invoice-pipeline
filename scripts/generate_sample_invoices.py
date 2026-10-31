"""Generate synthetic (fake) invoice PDFs with different layouts for testing a parser.

All vendors, customers, tax codes and prices are made up. Run:
    pip install reportlab
    python generate_sample_invoices.py
Outputs: sample_invoices/*.pdf and sample_invoices/expected.json (ground truth
for golden-file tests).
"""
import json
import os

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONT_DIR = "/usr/share/fonts/truetype/dejavu"  # change on your machine if needed
pdfmetrics.registerFont(TTFont("DV", f"{FONT_DIR}/DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DVB", f"{FONT_DIR}/DejaVuSans-Bold.ttf"))

W, H = A4
OUT = "sample_invoices"
os.makedirs(OUT, exist_ok=True)


def money(n):
    return f"{n:,}".replace(",", ".")  # Vietnamese style: 1.250.000


def totals(items, discount_pct=0):
    """items: (desc, unit, qty, price, vat%). Returns dict with all amounts."""
    lines = [dict(desc=d, unit=u, qty=q, unit_price=p, amount=q * p, vat_rate=v)
             for d, u, q, p, v in items]
    subtotal = sum(l["amount"] for l in lines)
    discount = round(subtotal * discount_pct / 100)
    vat_by_rate = {}
    for l in lines:
        share = l["amount"] - round(discount * l["amount"] / subtotal)
        vat_by_rate[l["vat_rate"]] = vat_by_rate.get(l["vat_rate"], 0) + share
    vat = {r: round(base * r / 100) for r, base in vat_by_rate.items()}
    return dict(items=lines, subtotal=subtotal, discount=discount,
                vat_by_rate=vat, vat_total=sum(vat.values()),
                grand_total=subtotal - discount + sum(vat.values()))


def header(c, inv, title="HÓA ĐƠN GIÁ TRỊ GIA TĂNG", lang="vi"):
    c.setFont("DVB", 11)
    c.drawString(40, H - 50, inv["vendor"])
    c.setFont("DV", 8.5)
    c.drawString(40, H - 65, inv["addr"])
    c.drawString(40, H - 78, ("Mã số thuế: " if lang == "vi" else "Tax ID: ") + inv["tax_code"])
    c.setFont("DVB", 15)
    c.drawCentredString(W / 2, H - 115, title)
    c.setFont("DV", 9)
    no, date = ("Số", "Ngày") if lang == "vi" else ("Invoice No.", "Date")
    c.drawCentredString(W / 2, H - 132, f"{no}: {inv['no']}    {date}: {inv['date']}")
    cust = "Khách hàng" if lang == "vi" else "Bill to"
    c.drawString(40, H - 155, f"{cust}: {inv['customer']}")


# ---------- Layout 1: gridded table, single VAT rate ----------
def layout_grid(c, inv, t):
    header(c, inv)
    cols = [40, 70, 290, 335, 380, 465, 555]
    y = H - 185
    c.setFont("DVB", 9)
    for i, h in enumerate(["STT", "Tên hàng hóa, dịch vụ", "ĐVT", "SL", "Đơn giá", "Thành tiền"]):
        c.drawString(cols[i] + 3, y - 14, h)
    top = y
    c.line(cols[0], y, cols[-1], y)
    y -= 22
    c.line(cols[0], y, cols[-1], y)
    c.setFont("DV", 9)
    for n, l in enumerate(t["items"], 1):
        c.drawString(cols[0] + 3, y - 15, str(n))
        c.drawString(cols[1] + 3, y - 15, l["desc"])
        c.drawString(cols[2] + 3, y - 15, l["unit"])
        c.drawRightString(cols[4] - 5, y - 15, str(l["qty"]))
        c.drawRightString(cols[5] - 5, y - 15, money(l["unit_price"]))
        c.drawRightString(cols[6] - 5, y - 15, money(l["amount"]))
        y -= 22
        c.line(cols[0], y, cols[-1], y)
    for x in cols:
        c.line(x, top, x, y)
    y -= 20
    rate = t["items"][0]["vat_rate"]
    for label, val, bold in [("Cộng tiền hàng", t["subtotal"], False),
                             (f"Thuế GTGT ({rate}%)", t["vat_total"], False),
                             ("Tổng cộng thanh toán", t["grand_total"], True)]:
        c.setFont("DVB" if bold else "DV", 9.5)
        c.drawString(330, y, label + ":")
        c.drawRightString(cols[-1] - 5, y, money(val))
        y -= 16


# ---------- Layout 2: per-line VAT column, mixed 8% / 10% ----------
def layout_mixed_vat(c, inv, t):
    header(c, inv)
    x = dict(stt=40, name=62, unit=250, qty=315, price=385, amt=470, vat=540)
    y = H - 190
    c.setFont("DVB", 8.5)
    c.drawString(x["stt"], y, "STT")
    c.drawString(x["name"], y, "Tên hàng")
    c.drawString(x["unit"], y, "ĐVT")
    c.drawRightString(x["qty"], y, "SL")
    c.drawRightString(x["price"], y, "Đơn giá")
    c.drawRightString(x["amt"], y, "Thành tiền")
    c.drawCentredString(x["vat"], y, "Thuế suất")
    c.line(40, y - 6, 570, y - 6)
    y -= 22
    c.setFont("DV", 9)
    for n, l in enumerate(t["items"], 1):
        c.drawString(x["stt"], y, str(n))
        c.drawString(x["name"], y, l["desc"])
        c.drawString(x["unit"], y, l["unit"])
        c.drawRightString(x["qty"], y, str(l["qty"]))
        c.drawRightString(x["price"], y, money(l["unit_price"]))
        c.drawRightString(x["amt"], y, money(l["amount"]))
        c.drawCentredString(x["vat"], y, f"{l['vat_rate']}%")
        y -= 18
    c.line(40, y + 8, 570, y + 8)
    y -= 12
    rows = [("Tổng tiền hàng", t["subtotal"])]
    rows += [(f"Thuế GTGT {r}%", v) for r, v in sorted(t["vat_by_rate"].items())]
    rows.append(("Tổng cộng thanh toán", t["grand_total"]))
    for i, (label, val) in enumerate(rows):
        c.setFont("DVB" if i == len(rows) - 1 else "DV", 9.5)
        c.drawString(330, y, label + ":")
        c.drawRightString(565, y, money(val))
        y -= 16


# ---------- Layout 3: no gridlines, non-standard headers ----------
def layout_plain(c, inv, t):
    header(c, inv, title="HÓA ĐƠN BÁN HÀNG")
    y = H - 195
    c.setFont("DVB", 9)
    c.drawString(40, y, "Diễn giải")
    c.drawRightString(330, y, "Số lượng")
    c.drawRightString(430, y, "Giá")
    c.drawRightString(540, y, "Tiền")
    c.line(40, y - 5, 540, y - 5)
    y -= 24
    c.setFont("DV", 9.5)
    for l in t["items"]:
        c.drawString(40, y, f"{l['desc']} ({l['unit']})")
        c.drawRightString(330, y, str(l["qty"]))
        c.drawRightString(430, y, money(l["unit_price"]))
        c.drawRightString(540, y, money(l["amount"]))
        y -= 22
    y -= 10
    for label, val, bold in [("Tạm tính", t["subtotal"], False),
                             ("Thuế VAT (10%)", t["vat_total"], False),
                             ("Tổng thanh toán", t["grand_total"], True)]:
        c.setFont("DVB" if bold else "DV", 10)
        c.drawString(350, y, label)
        c.drawRightString(540, y, money(val))
        y -= 18


# ---------- Layout 4: wrapped descriptions, jittered columns, mixed VAT ----------
def layout_wrapped(c, inv, t):
    header(c, inv)
    y = H - 190
    c.setFont("DVB", 8.5)
    c.drawString(40, y, "Mặt hàng / Quy cách")
    c.drawString(262, y, "SL")
    c.drawRightString(405, y, "Đ.Giá")
    c.drawRightString(488, y, "T.Tiền")
    c.drawString(512, y, "VAT")
    c.line(40, y - 6, 570, y - 6)
    y -= 22
    c.setFont("DV", 9)
    for i, l in enumerate(t["items"]):
        parts = simpleSplit(l["desc"], "DV", 9, 200)
        jitter = [0, 4, -3, 2, -2][i % 5]  # simulates misaligned columns
        c.drawString(40, y, parts[0])
        c.drawString(262 + jitter, y - 1, str(l["qty"]))
        c.drawRightString(405 + jitter, y - 1, money(l["unit_price"]))
        c.drawRightString(488, y - 2, money(l["amount"]))
        c.drawString(512, y, f"{l['vat_rate']}%")
        for extra in parts[1:]:
            y -= 12
            c.drawString(40, y, extra)
        y -= 20
    y -= 6
    rows = [("Cộng tiền hàng", t["subtotal"])]
    rows += [(f"GTGT {r}%", v) for r, v in sorted(t["vat_by_rate"].items())]
    rows.append(("TỔNG CỘNG", t["grand_total"]))
    for i, (label, val) in enumerate(rows):
        c.setFont("DVB" if i == len(rows) - 1 else "DV", 9.5)
        c.drawString(320, y, label)
        c.drawRightString(488, y, money(val))
        y -= 16


# ---------- Layout 5: English, item code column, discount ----------
def layout_english(c, inv, t):
    header(c, inv, title="TAX INVOICE", lang="en")
    y = H - 190
    c.setFont("DVB", 8.5)
    for xx, label, right in [(40, "Code", False), (100, "Description", False),
                             (350, "Qty", True), (430, "Unit Price", True),
                             (520, "Amount", True), (565, "Tax", True)]:
        (c.drawRightString if right else c.drawString)(xx, y, label)
    c.line(40, y - 6, 570, y - 6)
    y -= 22
    c.setFont("DV", 9)
    for i, l in enumerate(t["items"], 1):
        c.drawString(40, y, f"SKU{i:03d}")
        c.drawString(100, y, l["desc"])
        c.drawRightString(350, y, str(l["qty"]))
        c.drawRightString(430, y, money(l["unit_price"]))
        c.drawRightString(520, y, money(l["amount"]))
        c.drawRightString(565, y, f"{l['vat_rate']}%")
        y -= 18
    y -= 10
    rows = [("Subtotal", t["subtotal"]), ("Discount (5%)", -t["discount"]),
            ("VAT 10%", t["vat_total"]), ("Total Due (VND)", t["grand_total"])]
    for i, (label, val) in enumerate(rows):
        c.setFont("DVB" if i == len(rows) - 1 else "DV", 9.5)
        c.drawString(350, y, label)
        c.drawRightString(520, y, ("-" if val < 0 else "") + money(abs(val)))
        y -= 16


INVOICES = [
    dict(file="invoice_01_grid.pdf", fn=layout_grid, no="AP-000101", date="05/10/2026",
         vendor="Công ty TNHH Thực phẩm An Phát", tax_code="0312345001",
         addr="12 Đường Số 5, Quận 7, TP. Hồ Chí Minh", customer="Công ty ABC (dữ liệu mẫu)",
         items=[("Gạo ST25 túi 5kg", "túi", 20, 145000, 10), ("Dầu ăn 1L", "chai", 36, 52000, 10),
                ("Đường tinh luyện 1kg", "kg", 50, 24000, 10), ("Nước mắm 500ml", "chai", 24, 38000, 10)]),
    dict(file="invoice_02_mixed_vat.pdf", fn=layout_mixed_vat, no="MT-004455", date="12/10/2026",
         vendor="Công ty CP Siêu thị Minh Tâm", tax_code="0312345002",
         addr="88 Lê Lợi, TP. Thủ Đức, TP. Hồ Chí Minh", customer="Công ty ABC (dữ liệu mẫu)",
         items=[("Sữa tươi hộp 1L", "hộp", 48, 31000, 8), ("Bánh quy bơ 400g", "hộp", 30, 42000, 8),
                ("Nước rửa chén 750ml", "chai", 20, 36000, 10), ("Giấy vệ sinh lốc 10", "lốc", 40, 85000, 10),
                ("Nước suối 500ml", "thùng", 25, 78000, 8)]),
    dict(file="invoice_03_plain.pdf", fn=layout_plain, no="HB-2026/0731", date="18/10/2026",
         vendor="Công ty CP Vận tải Hòa Bình", tax_code="0312345003",
         addr="45 Quốc Lộ 1A, Quận 12, TP. Hồ Chí Minh", customer="Công ty ABC (dữ liệu mẫu)",
         items=[("Cước vận chuyển nội thành", "chuyến", 12, 850000, 10), ("Phí bốc xếp", "lượt", 12, 150000, 10),
                ("Phụ phí chờ hàng", "giờ", 5, 120000, 10)]),
    dict(file="invoice_04_wrapped.pdf", fn=layout_wrapped, no="VL-0098213", date="22/10/2026",
         vendor="Công ty TNHH Vật liệu Xây dựng Tiến Phát", tax_code="0312345004",
         addr="210 Nguyễn Văn Linh, Bình Chánh, TP. Hồ Chí Minh", customer="Công ty ABC (dữ liệu mẫu)",
         items=[("Xi măng PCB40 bao 50kg, loại dùng cho xây tô và đổ bê tông", "bao", 200, 92000, 10),
                ("Thép phi 10 cây dài 11,7m", "cây", 80, 148000, 10),
                ("Cát xây tô loại 1, xe 4 khối, giao tận công trình", "xe", 6, 1200000, 8),
                ("Sơn nước nội thất thùng 18L, màu trắng mờ, chống nấm mốc", "thùng", 8, 1650000, 10)]),
    dict(file="invoice_05_english.pdf", fn=layout_english, no="OS-77120", date="27/10/2026",
         vendor="Sunrise Office Supplies Co., Ltd", tax_code="0312345005", discount_pct=5,
         addr="3 Pasteur Street, District 3, Ho Chi Minh City", customer="ABC Company (sample data)",
         items=[("A4 paper ream 80gsm", "ream", 100, 68000, 10), ("Ballpoint pens (box of 20)", "box", 30, 45000, 10),
                ("Heavy-duty stapler", "pc", 10, 85000, 10)]),
    dict(file="invoice_06_wrong_total.pdf", fn=layout_grid, no="DL-550231", date="29/10/2026", tamper=True,
         vendor="Công ty TNHH Điện máy Đại Lợi", tax_code="0312345006",
         addr="67 Trường Chinh, Tân Bình, TP. Hồ Chí Minh", customer="Công ty ABC (dữ liệu mẫu)",
         items=[("Quạt đứng công nghiệp", "cái", 6, 1350000, 10), ("Ổ cắm điện 5m", "cái", 15, 95000, 10),
                ("Bóng đèn LED 12W", "cái", 40, 32000, 10)]),
]

expected = {}
for inv in INVOICES:
    t = totals(inv["items"], inv.get("discount_pct", 0))
    if inv.get("tamper"):  # print a wrong grand total on purpose (+10.000 VND)
        t["grand_total"] += 10000
    c = canvas.Canvas(os.path.join(OUT, inv["file"]), pagesize=A4)
    c.setTitle(f"Sample invoice {inv['no']}")
    inv["fn"](c, inv, t)
    c.setFont("DV", 7)
    c.drawString(40, 30, "DỮ LIỆU MẪU - KHÔNG PHẢI HÓA ĐƠN THẬT / SYNTHETIC SAMPLE, NOT A REAL INVOICE")
    c.save()
    expected[inv["file"]] = dict(invoice_no=inv["no"], date=inv["date"], vendor=inv["vendor"],
                                 expected_status="NEEDS_REVIEW" if inv.get("tamper") else "PARSED", **t)

with open(os.path.join(OUT, "expected.json"), "w", encoding="utf-8") as f:
    json.dump(expected, f, ensure_ascii=False, indent=2)
print("Generated", len(INVOICES), "invoices in", OUT)
