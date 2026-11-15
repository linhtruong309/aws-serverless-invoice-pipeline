using System.Globalization;
using Amazon.DynamoDBv2.Model;
using InvoiceApi.Domain;

namespace InvoiceApi.Data;

/// <summary>Turns a raw DynamoDB item (attribute name -> AttributeValue) into an Invoice.</summary>
public static class InvoiceMapper
{
    public static Invoice FromItem(IReadOnlyDictionary<string, AttributeValue> item) => new()
    {
        SourceKey = Str(item, "source_key") ?? throw new InvalidDataException("Item has no source_key"),
        Status = Str(item, "status") ?? InvoiceStatus.Failed,
        Bucket = Str(item, "bucket"),
        ReceivedAt = DateTimeOffset.TryParse(Str(item, "received_at"), CultureInfo.InvariantCulture,
            DateTimeStyles.AssumeUniversal, out var at) ? at : null,
        InvoiceNo = Str(item, "invoice_no"),
        Date = Str(item, "date"),
        Subtotal = Num(item, "subtotal"),
        Discount = Num(item, "discount"),
        GrandTotal = Num(item, "grand_total"),
        VatByRate = MapAttr(item, "vat_by_rate")
            .Select(kv => (kv.Key, Value: ToDecimal(kv.Value)))
            .Where(kv => kv.Value is not null)
            .ToDictionary(kv => kv.Key, kv => kv.Value!.Value),
        LineItems = ListAttr(item, "line_items")
            .Select(v => v.M)
            .OfType<Dictionary<string, AttributeValue>>()
            .Select(ToLineItem)
            .ToList(),
        Issues = ListAttr(item, "issues")
            .Select(v => v.S)
            .OfType<string>()
            .ToList(),
        ExtractionMethod = Str(item, "extraction_method"),
        LlmModel = Str(item, "llm_model"),
    };

    private static LineItem ToLineItem(Dictionary<string, AttributeValue> m) => new(
        Desc: Str(m, "desc"),
        Qty: Num(m, "qty"),
        UnitPrice: Num(m, "unit_price"),
        Amount: Num(m, "amount"),
        VatRate: Num(m, "vat_rate") is { } rate ? (int)rate : null);

    private static string? Str(IReadOnlyDictionary<string, AttributeValue> item, string name) =>
        item.TryGetValue(name, out var v) ? v.S : null;

    private static decimal? Num(IReadOnlyDictionary<string, AttributeValue> item, string name) =>
        item.TryGetValue(name, out var v) ? ToDecimal(v) : null;

    // The parser writes numbers as DynamoDB N; accept numeric strings too in case an LLM result slipped through
    private static decimal? ToDecimal(AttributeValue v) =>
        decimal.TryParse(v.N ?? v.S, NumberStyles.Number, CultureInfo.InvariantCulture, out var d) ? d : null;

    // SDK v4 leaves M and L null when the attribute is absent, so default to empty
    private static Dictionary<string, AttributeValue> MapAttr(IReadOnlyDictionary<string, AttributeValue> item, string name) =>
        item.TryGetValue(name, out var v) && v.M is not null ? v.M : [];

    private static List<AttributeValue> ListAttr(IReadOnlyDictionary<string, AttributeValue> item, string name) =>
        item.TryGetValue(name, out var v) && v.L is not null ? v.L : [];
}
