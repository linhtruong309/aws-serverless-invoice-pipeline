namespace InvoiceApi.Domain;

/// <summary>The status values written by the parser Lambda.</summary>
public static class InvoiceStatus
{
    public const string Parsed = "PARSED";
    public const string NeedsReview = "NEEDS_REVIEW";
    public const string Failed = "FAILED";

    public static readonly IReadOnlyList<string> All = [Parsed, NeedsReview, Failed];

    /// <summary>Accepts any casing ("needs_review") and returns the stored form, or null if unknown.</summary>
    public static string? Normalize(string? value)
    {
        if (string.IsNullOrWhiteSpace(value)) return null;
        var upper = value.Trim().ToUpperInvariant();
        return All.Contains(upper) ? upper : null;
    }
}
