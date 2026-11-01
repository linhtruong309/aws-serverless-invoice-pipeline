"""Extraction pipeline: rules first, LLM fallback only when the rules cannot read the layout."""
import llm_fallback
from invoice_parser import extract_text, parse_invoice, validate


def needs_fallback(inv):
    """True when the rules failed to *read* the invoice (not when the numbers do not add up).

    A wrong total is a data problem a human must resolve; an LLM would just copy the same
    wrong number, so it is not worth a model call.
    """
    return (
        not inv["line_items"]
        or inv["subtotal"] is None
        or inv["grand_total"] is None
        or not inv["invoice_no"]
        or not inv["date"]
    )


def extract_invoice(pdf_bytes, llm_client=None):
    inv = parse_invoice(pdf_bytes)
    inv["extraction_method"] = "rules"
    if not needs_fallback(inv):
        return inv

    text = extract_text(pdf_bytes)
    try:
        llm_inv = llm_fallback.extract_with_llm(text, client=llm_client)
    except Exception as exc:  # model unreachable, access denied, bad reply...
        inv["issues"].append(f"LLM fallback failed: {exc}")
        return inv

    llm_inv["extraction_method"] = "llm"
    llm_inv["llm_model"] = llm_fallback.MODEL_ID
    llm_inv["rule_based_issues"] = inv["issues"]
    llm_inv["issues"] = (
        ["extracted by LLM: human review required"]
        + validate(llm_inv)
        + llm_fallback.grounding_issues(llm_inv, text)
    )
    return llm_inv
