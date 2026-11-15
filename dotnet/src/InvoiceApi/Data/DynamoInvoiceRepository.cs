using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;
using InvoiceApi.Domain;

namespace InvoiceApi.Data;

/// <summary>Reads the invoices table written by the Python parser Lambda. Never writes.</summary>
public sealed class DynamoInvoiceRepository(IAmazonDynamoDB dynamo, string tableName) : IInvoiceRepository
{
    public async Task<Invoice?> GetAsync(string sourceKey, CancellationToken ct = default)
    {
        var response = await dynamo.GetItemAsync(new GetItemRequest
        {
            TableName = tableName,
            Key = new Dictionary<string, AttributeValue> { ["source_key"] = new() { S = sourceKey } },
        }, ct);

        return response.Item is { Count: > 0 } item ? InvoiceMapper.FromItem(item) : null;
    }

    public async Task<IReadOnlyList<Invoice>> ListAsync(string? status, CancellationToken ct = default)
    {
        var request = new ScanRequest { TableName = tableName };
        if (status is not null)
        {
            // "status" is a DynamoDB reserved word, so it goes through a placeholder
            request.FilterExpression = "#s = :s";
            request.ExpressionAttributeNames = new Dictionary<string, string> { ["#s"] = "status" };
            request.ExpressionAttributeValues = new Dictionary<string, AttributeValue> { [":s"] = new() { S = status } };
        }

        // A Scan returns at most 1 MB per call, so keep reading until there is no LastEvaluatedKey
        var invoices = new List<Invoice>();
        do
        {
            var page = await dynamo.ScanAsync(request, ct);
            invoices.AddRange((page.Items ?? []).Select(InvoiceMapper.FromItem));
            request.ExclusiveStartKey = page.LastEvaluatedKey is { Count: > 0 } next ? next : null;
        } while (request.ExclusiveStartKey is not null);

        return invoices;
    }
}
