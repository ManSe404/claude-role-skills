using System.Globalization;
using System.Text.RegularExpressions;

namespace Acme.Logistics.Common;

public static class Helpers
{
    public static string FormatDate(DateTime value)
    {
        return value.ToString("dd.MM.yyyy", CultureInfo.InvariantCulture);
    }

    public static string CleanText(string? value)
    {
        return Regex.Replace(value ?? "", @"\s+", " ").Trim();
    }

    public static decimal AddVat(decimal net)
    {
        return Math.Round(net * 1.20m, 2);
    }

    public static void Retry(Action action, int attempts = 3)
    {
        for (var attempt = 1; ; attempt++)
        {
            try
            {
                action();
                return;
            }
            catch (Exception) when (attempt < attempts)
            {
                Thread.Sleep(200 * attempt);
            }
        }
    }
}
