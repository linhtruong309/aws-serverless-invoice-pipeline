"""Golden-file tests for the rule-based parser, the validation rules, the LLM fallback
(with a fake Bedrock client, so no AWS is needed) and the Lambda handler."""
import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import llm_fallback
from extraction import extract_invoice, needs_fallback
from invoice_parser import parse_invoice, validate

SAMPLES = Path(__file__).resolve().parent.parent / "sample_invoices"
EXPECTED = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))
RULE_FILES = sorted(f for f, e in EXPECTED.items() if not e.get("needs_llm"))
LLM_FILE = "invoice_07_unfamiliar_layout.pdf"


def pdf_bytes(name):
    return (SAMPLES / name).read_bytes()


def line_tuples(items):
    return [(i["qty"], i["unit_price"], i["amount"], i["vat_rate"]) for i in items]


# ------------------------------------------------------------------ rule-based parser
@pytest.mark.parametrize("filename", RULE_FILES)
def test_golden_file(filename):
    want = EXPECTED[filename]
    got = parse_invoice(pdf_bytes(filename))

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
    got = parse_invoice(pdf_bytes("invoice_06_wrong_total.pdf"))
    assert any("grand total" in issue for issue in got["issues"])


def test_wrapped_description_is_joined():
    got = parse_invoice(pdf_bytes("invoice_04_wrapped.pdf"))
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


# ------------------------------------------------------------------ LLM fallback (fake Bedrock)
class FakeBedrock:
    """Stands in for the bedrock-runtime client and records every call."""

    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return {"output": {"message": {"content": [{"text": self.reply}]}}}


class ExplodingBedrock:
    def converse(self, **kwargs):
        raise AssertionError("the LLM must not be called for this invoice")


def good_reply():
    want = EXPECTED[LLM_FILE]
    return json.dumps({
        "invoice_no": want["invoice_no"], "date": want["date"],
        "line_items": [{k: i[k] for k in ("desc", "qty", "unit_price", "amount", "vat_rate")} for i in want["items"]],
        "subtotal": want["subtotal"], "discount": want["discount"],
        "vat_by_rate": want["vat_by_rate"], "grand_total": want["grand_total"],
    })


def test_unfamiliar_layout_defeats_the_rules():
    assert needs_fallback(parse_invoice(pdf_bytes(LLM_FILE)))


def test_llm_fallback_extracts_and_validates():
    want, fake = EXPECTED[LLM_FILE], FakeBedrock(good_reply())
    got = extract_invoice(pdf_bytes(LLM_FILE), llm_client=fake)

    assert got["extraction_method"] == "llm"
    assert line_tuples(got["line_items"]) == line_tuples(want["items"])
    assert got["grand_total"] == want["grand_total"]
    assert got["issues"] == ["extracted by LLM: human review required"]  # no arithmetic or grounding problems
    call = fake.calls[0]
    assert call["inferenceConfig"]["temperature"] == 0
    assert "untrusted" in call["system"][0]["text"]  # prompt-injection guard is in the prompt


def test_llm_not_called_when_rules_succeed():
    got = extract_invoice(pdf_bytes("invoice_01_grid.pdf"), llm_client=ExplodingBedrock())
    assert got["extraction_method"] == "rules" and got["issues"] == []


def test_llm_not_called_for_wrong_total():
    got = extract_invoice(pdf_bytes("invoice_06_wrong_total.pdf"), llm_client=ExplodingBedrock())
    assert got["extraction_method"] == "rules" and got["issues"]


def test_llm_invented_number_is_flagged():
    data = json.loads(good_reply())
    data["line_items"][0]["amount"] = 99999999
    got = extract_invoice(pdf_bytes(LLM_FILE), llm_client=FakeBedrock(json.dumps(data)))
    assert any("not found in the document text" in i for i in got["issues"])
    assert any("sum of lines" in i for i in got["issues"])


def test_llm_json_in_code_fence_is_accepted():
    got = extract_invoice(pdf_bytes(LLM_FILE), llm_client=FakeBedrock("```json\n" + good_reply() + "\n```"))
    assert got["extraction_method"] == "llm"


def test_llm_garbage_reply_is_reported_not_trusted():
    got = extract_invoice(pdf_bytes(LLM_FILE), llm_client=FakeBedrock("Sorry, I cannot help with that."))
    assert got["extraction_method"] == "rules"
    assert any("LLM fallback failed" in i for i in got["issues"])


def test_llm_decimal_string_is_rejected():
    data = json.loads(good_reply())
    data["subtotal"] = "12.5"
    got = extract_invoice(pdf_bytes(LLM_FILE), llm_client=FakeBedrock(json.dumps(data)))
    assert any("LLM fallback failed" in i for i in got["issues"])


def test_llm_call_error_is_reported():
    class Broken:
        def converse(self, **kwargs):
            raise RuntimeError("AccessDeniedException")

    got = extract_invoice(pdf_bytes(LLM_FILE), llm_client=Broken())
    assert any("AccessDeniedException" in i for i in got["issues"])


def test_as_int_accepts_grouped_numbers_but_not_decimals():
    assert llm_fallback.as_int("1.250.000", "x") == 1250000
    assert llm_fallback.as_int("1,250,000", "x") == 1250000
    with pytest.raises(llm_fallback.LLMError):
        llm_fallback.as_int("12.5", "x")


# ------------------------------------------------------------------ Lambda handler (fake S3 + DynamoDB + Bedrock)
def run_handler(monkeypatch, filename, bedrock_reply=None):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-2")
    fake = MagicMock()
    fake.get_object.return_value = {"Body": io.BytesIO(pdf_bytes(filename))}
    if bedrock_reply is not None:
        fake.converse.return_value = {"output": {"message": {"content": [{"text": bedrock_reply}]}}}
    fake_table = MagicMock()

    with patch("boto3.client", return_value=fake), patch("boto3.resource") as fake_resource:
        fake_resource.return_value.Table.return_value = fake_table
        sys.modules.pop("lambda_function", None)
        import lambda_function

        event = {"Records": [{"s3": {"bucket": {"name": "b"}, "object": {"key": filename}}}]}
        lambda_function.lambda_handler(event, None)
    return fake_table.put_item.call_args.kwargs["Item"]


def test_handler_saves_needs_review_item(monkeypatch):
    item = run_handler(monkeypatch, "invoice_06_wrong_total.pdf")
    assert item["status"] == "NEEDS_REVIEW"
    assert item["extraction_method"] == "rules"
    assert item["grand_total"] == EXPECTED["invoice_06_wrong_total.pdf"]["grand_total"]


def test_handler_marks_clean_rule_parse_as_parsed(monkeypatch):
    item = run_handler(monkeypatch, "invoice_01_grid.pdf")
    assert item["status"] == "PARSED" and item["extraction_method"] == "rules"


def test_handler_sends_llm_extraction_to_review_even_when_it_checks_out(monkeypatch):
    item = run_handler(monkeypatch, LLM_FILE, bedrock_reply=good_reply())
    assert item["status"] == "NEEDS_REVIEW"  # human oversight: LLM output is never auto-accepted
    assert item["extraction_method"] == "llm"
    assert item["grand_total"] == EXPECTED[LLM_FILE]["grand_total"]
    assert item["issues"] == ["extracted by LLM: human review required"]
