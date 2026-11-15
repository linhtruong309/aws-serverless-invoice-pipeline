using InvoiceApi.Domain;

namespace InvoiceApi.Tests;

/// <summary>Small invoices shaped like the ones the parser Lambda stores.</summary>
internal static class TestData
{
    public static Invoice Parsed(string key, decimal subtotal, decimal vat8, decimal vat10, decimal discount = 0,
        string receivedAt = "2026-11-01T10:00:00+00:00") => new()
    {
        SourceKey = key,
        Status = InvoiceStatus.Parsed,
        ReceivedAt = DateTimeOffset.Parse(receivedAt),
        InvoiceNo = $"INV-{key}",
        Subtotal = subtotal,
        Discount = discount,
        VatByRate = new Dictionary<string, decimal> { ["8"] = vat8, ["10"] = vat10 },
        GrandTotal = subtotal - discount + vat8 + vat10,
        ExtractionMethod = "rules",
    };

    public static Invoice NeedsReview(string key, string method = "rules",
        string receivedAt = "2026-11-02T10:00:00+00:00") => new()
    {
        SourceKey = key,
        Status = InvoiceStatus.NeedsReview,
        ReceivedAt = DateTimeOffset.Parse(receivedAt),
        Subtotal = 1_000_000,
        GrandTotal = 9_999_999, // wrong on purpose: this is why it needs review
        VatByRate = new Dictionary<string, decimal> { ["10"] = 100_000 },
        Issues = ["grand total does not match subtotal - discount + VAT"],
        ExtractionMethod = method,
    };

    public static Invoice Failed(string key) => new()
    {
        SourceKey = key,
        Status = InvoiceStatus.Failed,
        Issues = ["parser error: not a PDF"],
    };
}
