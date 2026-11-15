namespace InvoiceApi.Domain;

/// <summary>One invoice as the Python parser Lambda stored it in DynamoDB.</summary>
public sealed record Invoice
{
    public required string SourceKey { get; init; }
    public required string Status { get; init; }
    public string? Bucket { get; init; }
    public DateTimeOffset? ReceivedAt { get; init; }
    public string? InvoiceNo { get; init; }
    public string? Date { get; init; }
    public decimal? Subtotal { get; init; }
    public decimal? Discount { get; init; }
    public decimal? GrandTotal { get; init; }
    public IReadOnlyDictionary<string, decimal> VatByRate { get; init; } = new Dictionary<string, decimal>();
    public IReadOnlyList<LineItem> LineItems { get; init; } = [];
    public IReadOnlyList<string> Issues { get; init; } = [];
    public string? ExtractionMethod { get; init; }
    public string? LlmModel { get; init; }

    public decimal VatTotal => VatByRate.Values.Sum();
}

public sealed record LineItem(string? Desc, decimal? Qty, decimal? UnitPrice, decimal? Amount, int? VatRate);

/// <summary>Short row returned by GET /invoices, so the list stays small.</summary>
public sealed record InvoiceListItem(
    string SourceKey,
    string? InvoiceNo,
    string? Date,
    string Status,
    decimal? GrandTotal,
    string? ExtractionMethod,
    int IssueCount,
    DateTimeOffset? ReceivedAt)
{
    public static InvoiceListItem From(Invoice i) =>
        new(i.SourceKey, i.InvoiceNo, i.Date, i.Status, i.GrandTotal, i.ExtractionMethod, i.Issues.Count, i.ReceivedAt);
}

public sealed record InvoiceList(int Count, IReadOnlyList<InvoiceListItem> Items);

/// <summary>Response of GET /summary.</summary>
public sealed record InvoiceSummary(
    int TotalInvoices,
    IReadOnlyDictionary<string, int> ByStatus,
    IReadOnlyDictionary<string, int> ByExtractionMethod,
    ParsedTotals ParsedTotals,
    IReadOnlyList<string> NeedsAttention);

/// <summary>Money totals over PARSED invoices only: flagged invoices are not trusted yet.</summary>
public sealed record ParsedTotals(
    int InvoiceCount,
    decimal Subtotal,
    decimal Discount,
    IReadOnlyDictionary<string, decimal> VatByRate,
    decimal VatTotal,
    decimal GrandTotal);
