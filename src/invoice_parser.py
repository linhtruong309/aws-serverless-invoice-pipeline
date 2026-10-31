"""Parse invoice PDFs into structured data and check that the numbers add up.

Pure Python (only pdfplumber), no AWS imports, so it runs the same on your
laptop, in pytest and inside Lambda.
"""
import io
import re

import pdfplumber

NUM = r"\d[\d.]*"  # numbers like 1.250.000 (dot = thousands separator)

# One invoice line: [STT or SKU code] description qty unit_price amount [vat%]
ROW_RE = re.compile(
    rf"^(?:\d{{1,3}}\s+|SKU\d+\s+)?(?P<desc>.+?)\s+(?P<qty>\d+)\s+"
    rf"(?P<price>{NUM})\s+(?P<amount>{NUM})(?:\s+(?P<vat>\d+)%)?$"
)
SUBTOTAL_RE = re.compile(rf"^(?:cộng tiền hàng|tổng tiền hàng|tạm tính|subtotal)\s*:?\s*({NUM})$", re.I)
DISCOUNT_RE = re.compile(rf"^(?:discount|chiết khấu)\s*(?:\(\d+%\))?\s*:?\s*-?\s*({NUM})$", re.I)
VAT_RE = re.compile(rf"^(?:thuế gtgt|thuế vat|gtgt|vat)\s*\(?(\d+)%\)?\s*:?\s*({NUM})$", re.I)
TOTAL_RE = re.compile(
    rf"^(?:tổng cộng(?: thanh toán)?|tổng thanh toán|total due(?: \(vnd\))?)\s*:?\s*({NUM})$", re.I
)
NO_RE = re.compile(r"(?:Số|Invoice No\.)\s*:\s*([A-Za-z0-9/\-]+)")
DATE_RE = re.compile(r"(?:Ngày|Date)\s*:\s*(\d{2}/\d{2}/\d{4})")


def to_int(text):
    return int(text.replace(".", ""))


def extract_text(pdf_bytes):
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def parse_invoice(pdf_bytes):
    """Return a dict with header fields, line items, totals and a list of issues."""
    text = extract_text(pdf_bytes)
    no, date = NO_RE.search(text), DATE_RE.search(text)
    inv = {
        "invoice_no": no.group(1) if no else None,
        "date": date.group(1) if date else None,
        "line_items": [],
        "subtotal": None,
        "discount": 0,
        "vat_by_rate": {},  # {"8": 576000, "10": 4344000}
        "grand_total": None,
    }
    last_item, in_footer = None, False
    for line in (l.strip() for l in text.splitlines()):
        if not line:
            continue
        if m := SUBTOTAL_RE.match(line):
            inv["subtotal"], in_footer = to_int(m.group(1)), True
        elif m := DISCOUNT_RE.match(line):
            inv["discount"], in_footer = to_int(m.group(1)), True
        elif m := VAT_RE.match(line):
            inv["vat_by_rate"][m.group(1)] = to_int(m.group(2))
            in_footer = True
        elif m := TOTAL_RE.match(line):
            inv["grand_total"], in_footer = to_int(m.group(1)), True
        elif not in_footer and (m := ROW_RE.match(line)):
            last_item = {
                "desc": m.group("desc"),
                "qty": int(m.group("qty")),
                "unit_price": to_int(m.group("price")),
                "amount": to_int(m.group("amount")),
                "vat_rate": int(m.group("vat")) if m.group("vat") else None,
            }
            inv["line_items"].append(last_item)
        elif last_item is not None and not in_footer:
            last_item["desc"] += " " + line  # description wrapped onto a second line

    # Layouts without a per-line VAT column: use the single VAT rate in the footer
    if len(inv["vat_by_rate"]) == 1:
        only_rate = int(next(iter(inv["vat_by_rate"])))
        for item in inv["line_items"]:
            if item["vat_rate"] is None:
                item["vat_rate"] = only_rate

    inv["issues"] = validate(inv)
    return inv


def validate(inv):
    """Cross-check the parsed numbers. Any message returned means 'needs human review'."""
    issues, items = [], inv["line_items"]
    if not inv["invoice_no"]:
        issues.append("missing invoice number")
    if not inv["date"]:
        issues.append("missing date")
    if not items:
        issues.append("no line items found")
    if inv["subtotal"] is None:
        issues.append("missing subtotal")
    if inv["grand_total"] is None:
        issues.append("missing grand total")

    for n, item in enumerate(items, 1):
        if item["qty"] * item["unit_price"] != item["amount"]:
            issues.append(f"line {n}: qty x unit price does not equal amount")

    if items and inv["subtotal"] is not None:
        line_sum = sum(i["amount"] for i in items)
        if line_sum != inv["subtotal"]:
            issues.append(f"sum of lines {line_sum} != subtotal {inv['subtotal']}")

    if inv["subtotal"] is not None and inv["grand_total"] is not None:
        expected = inv["subtotal"] - inv["discount"] + sum(inv["vat_by_rate"].values())
        if expected != inv["grand_total"]:
            issues.append(f"subtotal - discount + VAT = {expected} != grand total {inv['grand_total']}")

    # Per-rate VAT check (allow 1 VND of rounding per line)
    base_by_rate = {}
    for item in items:
        if item["vat_rate"] is not None:
            key = str(item["vat_rate"])
            base_by_rate[key] = base_by_rate.get(key, 0) + item["amount"]
    if base_by_rate and inv["subtotal"]:
        factor = (inv["subtotal"] - inv["discount"]) / inv["subtotal"]
        for rate, base in base_by_rate.items():
            expected_vat = round(base * factor * int(rate) / 100)
            got = inv["vat_by_rate"].get(rate)
            if got is None or abs(got - expected_vat) > len(items):
                issues.append(f"VAT {rate}%: expected about {expected_vat}, found {got}")
    return issues
