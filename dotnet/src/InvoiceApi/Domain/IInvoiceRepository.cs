namespace InvoiceApi.Domain;

/// <summary>Read-only access to stored invoices. The service depends on this, not on DynamoDB.</summary>
public interface IInvoiceRepository
{
    Task<Invoice?> GetAsync(string sourceKey, CancellationToken ct = default);

    /// <param name="status">Stored status value to filter on, or null for every invoice.</param>
    Task<IReadOnlyList<Invoice>> ListAsync(string? status, CancellationToken ct = default);
}
