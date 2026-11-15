using Amazon.DynamoDBv2.Model;
using InvoiceApi.Data;

namespace InvoiceApi.Tests;

public class InvoiceMapperTests
{
    private static AttributeValue S(string s) => new() { S = s };
    private static AttributeValue N(string n) => new() { N = n };

    [Fact]
    public void Maps_a_full_item_written_by_the_parser_lambda()
    {
        var item = new Dictionary<string, AttributeValue>
        {
            ["source_key"] = S("invoice_02_mixed_vat.pdf"),
            ["bucket"] = S("invoice-tf-input-abcd"),
            ["status"] = S("PARSED"),
            ["received_at"] = S("2026-11-14T03:00:00.123456+00:00"),
            ["invoice_no"] = S("MT-004455"),
            ["date"] = S("12/10/2026"),
            ["subtotal"] = N("2000000"),
            ["discount"] = N("0"),
            ["grand_total"] = N("2180000"),
            ["vat_by_rate"] = new() { M = new() { ["8"] = N("80000"), ["10"] = N("100000") } },
            ["line_items"] = new()
            {
                L =
                [
                    new() { M = new() { ["desc"] = S("Sữa tươi hộp 1L"), ["qty"] = N("48"),
                        ["unit_price"] = N("31000"), ["amount"] = N("1488000"), ["vat_rate"] = N("8") } },
                ],
            },
            ["issues"] = new() { L = [] },
            ["extraction_method"] = S("rules"),
        };

        var invoice = InvoiceMapper.FromItem(item);

        Assert.Equal("invoice_02_mixed_vat.pdf", invoice.SourceKey);
        Assert.Equal("PARSED", invoice.Status);
        // Python's isoformat() keeps microseconds; they must survive the round trip
        Assert.Equal("2026-11-14T03:00:00.1234560+00:00", invoice.ReceivedAt?.ToString("O"));
        Assert.Equal("MT-004455", invoice.InvoiceNo);
        Assert.Equal(2_180_000m, invoice.GrandTotal);
        Assert.Equal(180_000m, invoice.VatTotal);
        var line = Assert.Single(invoice.LineItems);
        Assert.Equal("Sữa tươi hộp 1L", line.Desc);
        Assert.Equal(48m, line.Qty);
        Assert.Equal(8, line.VatRate);
        Assert.Empty(invoice.Issues);
    }

    [Fact]
    public void A_failed_item_with_only_issues_maps_without_errors()
    {
        var item = new Dictionary<string, AttributeValue>
        {
            ["source_key"] = S("not_a_pdf.pdf"),
            ["status"] = S("FAILED"),
            ["issues"] = new() { L = [S("parser error: not a PDF")] },
        };

        var invoice = InvoiceMapper.FromItem(item);

        Assert.Equal("FAILED", invoice.Status);
        Assert.Null(invoice.GrandTotal);
        Assert.Empty(invoice.LineItems);
        Assert.Empty(invoice.VatByRate);
        Assert.Equal("parser error: not a PDF", Assert.Single(invoice.Issues));
    }

    [Fact]
    public void An_item_without_source_key_is_rejected()
    {
        var item = new Dictionary<string, AttributeValue> { ["status"] = S("PARSED") };

        Assert.Throws<InvalidDataException>(() => InvoiceMapper.FromItem(item));
    }
}
