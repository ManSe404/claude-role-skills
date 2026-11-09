using Acme.Logistics.Common;
using Acme.Logistics.Domain;
using Acme.Logistics.Infrastructure;
using Acme.Logistics.Shipments;

namespace Acme.Logistics.Billing;

public class BillingService
{
    private readonly Database _database;

    public BillingService(Database database)
    {
        _database = database;
    }

    public async Task<Invoice> IssueInvoiceAsync(Shipment shipment)
    {
        if (shipment.Status != ShipmentStatus.Delivered)
        {
            throw new InvalidOperationException("Only delivered shipments can be invoiced.");
        }

        var number = await NextNumberAsync();
        var total = Helpers.AddVat(shipment.Price.Amount);
        var invoice = new Invoice
        {
            Number = number,
            ShipmentId = shipment.Id,
            Net = shipment.Price,
            Vat = Money.Rsd(total - shipment.Price.Amount),
            IssuedAt = DateTime.UtcNow,
        };

        await _database.ExecuteAsync(
            "INSERT INTO invoices (number, shipment_id, net, vat, issued_at) " +
            "VALUES (@Number, @ShipmentId, @Net, @Vat, @IssuedAt)",
            new { invoice.Number, invoice.ShipmentId, Net = invoice.Net.Amount, Vat = invoice.Vat.Amount, invoice.IssuedAt });
        return invoice;
    }

    public async Task<IReadOnlyList<Invoice>> ListForShipmentAsync(Guid shipmentId)
    {
        var rows = await _database.QueryAsync<InvoiceRow>(
            "SELECT number, shipment_id, net, vat, issued_at, credited FROM invoices WHERE shipment_id = @shipmentId",
            new { shipmentId });
        return rows.Select(ToInvoice).ToList();
    }

    public async Task CreditAsync(string number)
    {
        await _database.ExecuteAsync(
            "UPDATE invoices SET credited = true WHERE number = @number",
            new { number = Helpers.CleanText(number) });
    }

    private async Task<string> NextNumberAsync()
    {
        var next = await _database.QuerySingleAsync<long>("SELECT nextval('invoice_numbers')");
        return $"ACME-{DateTime.UtcNow:yyyy}-{next:000000}";
    }

    private static Invoice ToInvoice(InvoiceRow row)
    {
        return new Invoice
        {
            Number = row.Number,
            ShipmentId = row.ShipmentId,
            Net = Money.Rsd(row.Net),
            Vat = Money.Rsd(row.Vat),
            IssuedAt = row.IssuedAt,
            Credited = row.Credited,
        };
    }

    private record InvoiceRow(string Number, Guid ShipmentId, decimal Net, decimal Vat, DateTime IssuedAt, bool Credited);
}
