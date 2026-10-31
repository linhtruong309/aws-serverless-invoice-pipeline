"""Golden-file tests: parse each sample PDF and compare with the known-correct answers
in sample_invoices/expected.json. No AWS needed."""
import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from invoice_parser import parse_invoice, validate

SAMPLES = Path(__file__).resolve().parent.parent / "sample_invoices"
EXPECTED = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))


def line_tuples(items):
    return [(i["qty"], i["unit_price"], i["amount"], i["vat_rate"]) for i in items]


@pytest.mark.parametrize("filename", sorted(EXPECTED))
def test_golden_file(filename):
    want = EXPECTED[filename]
    got = parse_invoice((SAMPLES / filename).read_bytes())

    assert got["invoice_no"] == want["invoice_no"]
    assert got["date"] == want["date"]
    assert line_tuples(got["line_items"]) == line_tuples(want["items"])
    assert got["subtotal"] == want["subtotal"]
    assert got["discount"] == want["discount"]
    assert got["vat_by_rate"] == want["vat_by_rate"]
    assert got["grand_total"] == want["grand_total"]

    status = "PARSED" if not got["issues"] else "NEEDS_REVIEW"
    assert status == want["expected_status"]


def test_wrong_total_is_flagged_for_review():
    got = parse_invoice((SAMPLES / "invoice_06_wrong_total.pdf").read_bytes())
    assert any("grand total" in issue for issue in got["issues"])


def test_wrapped_description_is_joined():
    got = parse_invoice((SAMPLES / "invoice_04_wrapped.pdf").read_bytes())
    assert got["line_items"][0]["desc"].endswith("xây tô và đổ bê tông")


def make_invoice(**overrides):
    inv = {
        "invoice_no": "X-1", "date": "01/01/2026",
        "line_items": [{"desc": "a", "qty": 2, "unit_price": 1000, "amount": 2000, "vat_rate": 10}],
        "subtotal": 2000, "discount": 0, "vat_by_rate": {"10": 200}, "grand_total": 2200,
    }
    inv.update(overrides)
    return inv


def test_validate_accepts_consistent_invoice():
    assert validate(make_invoice()) == []


def test_validate_catches_line_math_error():
    bad = make_invoice(line_items=[{"desc": "a", "qty": 2, "unit_price": 1000, "amount": 2500, "vat_rate": 10}])
    assert any("qty x unit price" in i for i in validate(bad))


def test_validate_catches_subtotal_mismatch():
    assert any("subtotal" in i for i in validate(make_invoice(subtotal=1999)))


def test_validate_catches_missing_total():
    assert "missing grand total" in validate(make_invoice(grand_total=None))


def test_validate_catches_wrong_vat_amount():
    assert any("VAT 10%" in i for i in validate(make_invoice(vat_by_rate={"10": 900}, grand_total=2900)))


def test_non_pdf_input_raises():
    with pytest.raises(Exception):
        parse_invoice(b"this is not a pdf")


def test_handler_saves_needs_review_item(monkeypatch):
    """Run the real Lambda handler with S3 and DynamoDB replaced by fakes."""
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-2")
    pdf = (SAMPLES / "invoice_06_wrong_total.pdf").read_bytes()
    fake_s3 = MagicMock()
    fake_s3.get_object.return_value = {"Body": io.BytesIO(pdf)}
    fake_table = MagicMock()

    with patch("boto3.client", return_value=fake_s3), patch("boto3.resource") as fake_resource:
        fake_resource.return_value.Table.return_value = fake_table
        sys.modules.pop("lambda_function", None)
        import lambda_function

        event = {"Records": [{"s3": {"bucket": {"name": "b"}, "object": {"key": "invoice_06_wrong_total.pdf"}}}]}
        lambda_function.lambda_handler(event, None)

    item = fake_table.put_item.call_args.kwargs["Item"]
    assert item["status"] == "NEEDS_REVIEW"
    assert item["source_key"] == "invoice_06_wrong_total.pdf"
    assert item["grand_total"] == EXPECTED["invoice_06_wrong_total.pdf"]["grand_total"]
