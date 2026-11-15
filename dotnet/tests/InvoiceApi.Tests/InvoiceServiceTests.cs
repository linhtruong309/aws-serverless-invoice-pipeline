using InvoiceApi.Domain;
using Moq;

namespace InvoiceApi.Tests;

public class InvoiceServiceTests
{
    private readonly Mock<IInvoiceRepository> _repo = new(MockBehavior.Strict);
    private readonly InvoiceService _service;

    public InvoiceServiceTests() => _service = new InvoiceService(_repo.Object);

    private void RepoReturns(string? status, params Invoice[] invoices) =>
        _repo.Setup(r => r.ListAsync(status, It.IsAny<CancellationToken>())).ReturnsAsync(invoices);

    [Fact]
    public async Task List_without_status_returns_every_invoice_newest_first()
    {
        RepoReturns(null,
            TestData.Parsed("old.pdf", 100, 0, 10, receivedAt: "2026-11-01T08:00:00+00:00"),
            TestData.Parsed("new.pdf", 100, 0, 10, receivedAt: "2026-11-03T08:00:00+00:00"),
            TestData.Failed("broken.pdf")); // no received_at: goes last

        var result = await _service.ListAsync(status: null);

        Assert.Equal(3, result.Count);
        Assert.Equal(new[] { "new.pdf", "old.pdf", "broken.pdf" }, result.Items.Select(i => i.SourceKey));
    }

    [Theory]
    [InlineData("NEEDS_REVIEW")]
    [InlineData("needs_review")]
    [InlineData("  Needs_Review ")]
    public async Task List_normalizes_status_before_querying_the_repository(string input)
    {
        RepoReturns(InvoiceStatus.NeedsReview, TestData.NeedsReview("a.pdf"));

        var result = await _service.ListAsync(input);

        Assert.Equal("a.pdf", Assert.Single(result.Items).SourceKey);
        _repo.Verify(r => r.ListAsync(InvoiceStatus.NeedsReview, It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task List_rejects_an_unknown_status_without_touching_the_repository()
    {
        var ex = await Assert.ThrowsAsync<UnknownStatusException>(() => _service.ListAsync("APPROVED"));

        Assert.Contains("PARSED, NEEDS_REVIEW, FAILED", ex.Message);
        _repo.VerifyNoOtherCalls();
    }

    [Fact]
    public async Task List_item_carries_the_issue_count()
    {
        RepoReturns(null, TestData.NeedsReview("a.pdf"));

        var item = Assert.Single((await _service.ListAsync(null)).Items);

        Assert.Equal(1, item.IssueCount);
    }

    [Fact]
    public async Task Get_returns_null_when_the_key_does_not_exist()
    {
        _repo.Setup(r => r.GetAsync("missing.pdf", It.IsAny<CancellationToken>())).ReturnsAsync((Invoice?)null);

        Assert.Null(await _service.GetAsync("missing.pdf"));
    }

    [Fact]
    public async Task Summary_counts_every_status_including_zero()
    {
        RepoReturns(null, TestData.Parsed("a.pdf", 100, 0, 10), TestData.Parsed("b.pdf", 200, 16, 0));

        var summary = await _service.GetSummaryAsync();

        Assert.Equal(2, summary.TotalInvoices);
        Assert.Equal(2, summary.ByStatus[InvoiceStatus.Parsed]);
        Assert.Equal(0, summary.ByStatus[InvoiceStatus.NeedsReview]);
        Assert.Equal(0, summary.ByStatus[InvoiceStatus.Failed]);
        Assert.Empty(summary.NeedsAttention);
    }

    [Fact]
    public async Task Summary_money_totals_include_only_parsed_invoices()
    {
        RepoReturns(null,
            TestData.Parsed("a.pdf", subtotal: 1_000_000, vat8: 0, vat10: 100_000),
            TestData.Parsed("b.pdf", subtotal: 500_000, vat8: 16_000, vat10: 30_000, discount: 50_000),
            TestData.NeedsReview("c.pdf"),
            TestData.Failed("d.pdf"));

        var totals = (await _service.GetSummaryAsync()).ParsedTotals;

        Assert.Equal(2, totals.InvoiceCount);
        Assert.Equal(1_500_000m, totals.Subtotal);
        Assert.Equal(50_000m, totals.Discount);
        Assert.Equal(16_000m, totals.VatByRate["8"]);
        Assert.Equal(130_000m, totals.VatByRate["10"]);
        Assert.Equal(146_000m, totals.VatTotal);
        // 1,100,000 + (500,000 - 50,000 + 46,000); c.pdf's wrong 9,999,999 must not leak in
        Assert.Equal(1_596_000m, totals.GrandTotal);
    }

    [Fact]
    public async Task Summary_lists_flagged_invoices_and_counts_extraction_methods()
    {
        RepoReturns(null,
            TestData.Parsed("a.pdf", 100, 0, 10),
            TestData.NeedsReview("z.pdf", method: "llm"),
            TestData.Failed("m.pdf"));

        var summary = await _service.GetSummaryAsync();

        Assert.Equal(new[] { "m.pdf", "z.pdf" }, summary.NeedsAttention);
        Assert.Equal(1, summary.ByExtractionMethod["rules"]);
        Assert.Equal(1, summary.ByExtractionMethod["llm"]);
    }

    [Fact]
    public async Task Summary_of_an_empty_table_is_all_zeros()
    {
        RepoReturns(null);

        var summary = await _service.GetSummaryAsync();

        Assert.Equal(0, summary.TotalInvoices);
        Assert.Equal(0m, summary.ParsedTotals.GrandTotal);
        Assert.Empty(summary.ParsedTotals.VatByRate);
    }
}
