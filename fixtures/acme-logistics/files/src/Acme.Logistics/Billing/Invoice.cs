using Acme.Logistics.Domain;

namespace Acme.Logistics.Billing;

public class Invoice
{
    public string Number { get; init; } = "";
    public Guid ShipmentId { get; init; }
    public Money Net { get; init; } = Money.Zero;
    public Money Vat { get; init; } = Money.Zero;
    public Money Total => Net.Add(Vat);
    public DateTime IssuedAt { get; init; }
    public bool Credited { get; init; }
}
