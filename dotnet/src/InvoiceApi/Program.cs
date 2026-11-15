using System.Text.Json;
using Amazon.DynamoDBv2;
using InvoiceApi.Data;
using InvoiceApi.Domain;

var builder = WebApplication.CreateBuilder(args);

// Inside Lambda this swaps Kestrel for the API Gateway HTTP API adapter; on a laptop it does nothing
builder.Services.AddAWSLambdaHosting(LambdaEventSource.HttpApi);

// snake_case JSON so field names match the DynamoDB items and the Python side
builder.Services.ConfigureHttpJsonOptions(o =>
    o.SerializerOptions.PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower);

builder.Services.AddSingleton<IAmazonDynamoDB>(_ => new AmazonDynamoDBClient());
builder.Services.AddSingleton<IInvoiceRepository>(sp => new DynamoInvoiceRepository(
    sp.GetRequiredService<IAmazonDynamoDB>(),
    builder.Configuration["TABLE_NAME"] ?? throw new InvalidOperationException("TABLE_NAME is not set")));
builder.Services.AddSingleton<InvoiceService>();
builder.Services.AddProblemDetails();

var app = builder.Build();
app.UseExceptionHandler();

app.MapGet("/health", () => Results.Ok(new { status = "ok" }));

app.MapGet("/invoices", async (string? status, InvoiceService service, CancellationToken ct) =>
{
    try
    {
        return Results.Ok(await service.ListAsync(status, ct));
    }
    catch (UnknownStatusException ex)
    {
        return Results.Problem(ex.Message, statusCode: StatusCodes.Status400BadRequest);
    }
});

// {**sourceKey} also matches keys that contain "/", e.g. "2026/10/invoice_01.pdf"
app.MapGet("/invoices/{**sourceKey}", async (string sourceKey, InvoiceService service, CancellationToken ct) =>
    await service.GetAsync(Uri.UnescapeDataString(sourceKey), ct) is { } invoice
        ? Results.Ok(invoice)
        : Results.Problem($"No invoice with source_key '{sourceKey}'.", statusCode: StatusCodes.Status404NotFound));

app.MapGet("/summary", async (InvoiceService service, CancellationToken ct) =>
    Results.Ok(await service.GetSummaryAsync(ct)));

app.Run();

// Lets the test project start the app in memory with WebApplicationFactory<Program>
public partial class Program { }
