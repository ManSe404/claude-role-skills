using Acme.Logistics.Domain;

namespace Acme.Logistics.Shipments;

public enum ShipmentStatus
{
    Booked,
    InTransit,
    Delivered,
    Cancelled,
}

public class Shipment
{
    public Guid Id { get; init; }
    public string TrackingNumber { get; init; } = "";
    public string Sender { get; init; } = "";
    public string Recipient { get; init; } = "";
    public string Address { get; init; } = "";
    public Parcel Parcel { get; init; } = null!;
    public Money Price { get; set; } = Money.Zero;
    public ShipmentStatus Status { get; set; }
    public DateTime BookedAt { get; init; }
}
