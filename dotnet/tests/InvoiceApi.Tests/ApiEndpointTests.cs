using System.Net;
using System.Text.Json;
using InvoiceApi.Domain;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using Moq;

namespace InvoiceApi.Tests;

/// <summary>Runs the real HTTP pipeline in memory, with DynamoDB replaced by a mock repository.</summary>
public class ApiEndpointTests(WebApplicationFactory<Program> factory) : IClassFixture<WebApplicationFactory<Program>>
{
    private readonly Mock<IInvoiceRepository> _repo = new();

    private HttpClient CreateClient() => factory
        .WithWebHostBuilder(b => b.ConfigureTestServices(s => s.AddSingleton(_repo.Object)))
        .CreateClient();

    private static async Task<JsonElement> ReadJson(HttpResponseMessage response) =>
        JsonDocument.Parse(await response.Content.ReadAsStringAsync()).RootElement;

    [Fact]
    public async Task Health_returns_ok()
    {
        var response = await CreateClient().GetAsync("/health");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task Invoices_endpoint_returns_snake_case_json()
    {
        _repo.Setup(r => r.ListAsync(null, It.IsAny<CancellationToken>()))
            .ReturnsAsync(new[] { TestData.Parsed("a.pdf", 100, 0, 10) });

        var json = await ReadJson(await CreateClient().GetAsync("/invoices"));

        Assert.Equal(1, json.GetProperty("count").GetInt32());
        var first = json.GetProperty("items")[0];
        Assert.Equal("a.pdf", first.GetProperty("source_key").GetString());
        Assert.Equal(110m, first.GetProperty("grand_total").GetDecimal());
    }

    [Fact]
    public async Task Unknown_status_returns_400_problem_details()
    {
        var response = await CreateClient().GetAsync("/invoices?status=approved");

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal("application/problem+json", response.Content.Headers.ContentType?.MediaType);
    }

    [Fact]
    public async Task Missing_invoice_returns_404()
    {
        _repo.Setup(r => r.GetAsync("nope.pdf", It.IsAny<CancellationToken>())).ReturnsAsync((Invoice?)null);

        var response = await CreateClient().GetAsync("/invoices/nope.pdf");

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    [Fact]
    public async Task Source_keys_with_slashes_reach_the_repository_intact()
    {
        _repo.Setup(r => r.GetAsync("2026/10/a.pdf", It.IsAny<CancellationToken>()))
            .ReturnsAsync(TestData.Parsed("2026/10/a.pdf", 100, 0, 10));

        var response = await CreateClient().GetAsync("/invoices/2026/10/a.pdf");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("2026/10/a.pdf", (await ReadJson(response)).GetProperty("source_key").GetString());
    }

    [Fact]
    public async Task Summary_endpoint_returns_parsed_totals()
    {
        _repo.Setup(r => r.ListAsync(null, It.IsAny<CancellationToken>()))
            .ReturnsAsync(new[] { TestData.Parsed("a.pdf", 1_000, 0, 100), TestData.NeedsReview("b.pdf") });

        var json = await ReadJson(await CreateClient().GetAsync("/summary"));

        Assert.Equal(2, json.GetProperty("total_invoices").GetInt32());
        Assert.Equal(1_100m, json.GetProperty("parsed_totals").GetProperty("grand_total").GetDecimal());
        Assert.Equal("b.pdf", json.GetProperty("needs_attention")[0].GetString());
    }
}
