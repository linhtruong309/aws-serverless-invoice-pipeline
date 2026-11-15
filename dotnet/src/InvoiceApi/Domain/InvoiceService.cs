namespace InvoiceApi.Domain;

/// <summary>Business rules for the query API: filtering, ordering and the summary report.</summary>
public sealed class InvoiceService(IInvoiceRepository repository)
{
    /// <summary>Lists invoices, newest first. Throws if the status filter is not a known status.</summary>
    public async Task<InvoiceList> ListAsync(string? status, CancellationToken ct = default)
    {
        string? normalized = null;
        if (!string.IsNullOrWhiteSpace(status))
        {
            normalized = InvoiceStatus.Normalize(status)
                ?? throw new UnknownStatusException(status);
        }

        var invoices = await repository.ListAsync(normalized, ct);
        var items = invoices
            .OrderByDescending(i => i.ReceivedAt ?? DateTimeOffset.MinValue)
            .ThenBy(i => i.SourceKey, StringComparer.Ordinal)
            .Select(InvoiceListItem.From)
            .ToList();
        return new InvoiceList(items.Count, items);
    }

    public Task<Invoice?> GetAsync(string sourceKey, CancellationToken ct = default) =>
        repository.GetAsync(sourceKey, ct);

    public async Task<InvoiceSummary> GetSummaryAsync(CancellationToken ct = default)
    {
        var invoices = await repository.ListAsync(status: null, ct);

        // Every known status appears, even with a count of 0, so clients get a stable shape
        var byStatus = InvoiceStatus.All.ToDictionary(s => s, _ => 0);
        foreach (var i in invoices)
            byStatus[i.Status] = byStatus.GetValueOrDefault(i.Status) + 1;

        var byMethod = invoices
            .Where(i => i.ExtractionMethod is not null)
            .GroupBy(i => i.ExtractionMethod!)
            .OrderBy(g => g.Key, StringComparer.Ordinal)
            .ToDictionary(g => g.Key, g => g.Count());

        var parsed = invoices.Where(i => i.Status == InvoiceStatus.Parsed).ToList();
        var vatByRate = parsed
            .SelectMany(i => i.VatByRate)
            .GroupBy(kv => kv.Key)
            .OrderBy(g => int.TryParse(g.Key, out var rate) ? rate : int.MaxValue)
            .ToDictionary(g => g.Key, g => g.Sum(kv => kv.Value));

        var totals = new ParsedTotals(
            InvoiceCount: parsed.Count,
            Subtotal: parsed.Sum(i => i.Subtotal ?? 0),
            Discount: parsed.Sum(i => i.Discount ?? 0),
            VatByRate: vatByRate,
            VatTotal: vatByRate.Values.Sum(),
            GrandTotal: parsed.Sum(i => i.GrandTotal ?? 0));

        var needsAttention = invoices
            .Where(i => i.Status != InvoiceStatus.Parsed)
            .Select(i => i.SourceKey)
            .Order(StringComparer.Ordinal)
            .ToList();

        return new InvoiceSummary(invoices.Count, byStatus, byMethod, totals, needsAttention);
    }
}

public sealed class UnknownStatusException(string status)
    : ArgumentException($"Unknown status '{status}'. Use one of: {string.Join(", ", InvoiceStatus.All)}.")
{
    public string Status { get; } = status;
}
