using System.Net.Http.Json;
using Acme.Logistics.Billing;
using Acme.Logistics.Common;
using Acme.Logistics.Domain;
using Acme.Logistics.Infrastructure;

namespace Acme.Logistics.Shipments;

public record BookShipmentRequest(
    string Sender,
    string Recipient,
    string Address,
    decimal WeightKg,
    int LengthCm,
    int WidthCm,
    int HeightCm,
    bool Express,
    bool RemoteZone);

public record TrackingUpdate(string Status, string Location);

public record TrackingAnswer(string Status, string Location);

public class ShipmentService
{
    private const decimal MaxWeightKg = 70m;
    private const int MaxSideCm = 180;

    private readonly ShipmentRepository _repository;
    private readonly BillingService _billing;
    private readonly MessageBus _bus;
    private readonly HttpClient _http;
    private readonly Database _database;

    public ShipmentService(
        ShipmentRepository repository,
        BillingService billing,
        MessageBus bus,
        HttpClient http,
        Database database)
    {
        _repository = repository;
        _billing = billing;
        _bus = bus;
        _http = http;
        _database = database;
    }

    public async Task<Shipment> BookAsync(BookShipmentRequest request)
    {
        Validate(request);

        var parcel = new Parcel(
            Guid.NewGuid(),
            request.WeightKg,
            request.LengthCm,
            request.WidthCm,
            request.HeightCm);
        var price = PricingRules.Quote(parcel, request.Express, request.RemoteZone);
        var shipment = new Shipment
        {
            Id = Guid.NewGuid(),
            TrackingNumber = NewTrackingNumber(),
            Sender = Helpers.CleanText(request.Sender),
            Recipient = Helpers.CleanText(request.Recipient),
            Address = Helpers.CleanText(request.Address),
            Parcel = parcel,
            Price = price,
            Status = ShipmentStatus.Booked,
            BookedAt = DateTime.UtcNow,
        };

        await _repository.InsertAsync(ToRow(shipment));
        _bus.Publish("shipment.booked", new { id = shipment.Id, tracking = shipment.TrackingNumber });
        return shipment;
    }

    public async Task<Shipment?> GetAsync(Guid id)
    {
        var row = await _repository.FindAsync(id);
        return row is null ? null : ToShipment(row);
    }

    public async Task<IReadOnlyList<Shipment>> ListForRecipientAsync(string recipient)
    {
        var rows = await _repository.ListByRecipientAsync(recipient);
        return rows.Select(ToShipment).ToList();
    }

    public async Task<IReadOnlyList<Shipment>> ListInTransitAsync()
    {
        var rows = await _repository.ListByStatusAsync(ShipmentStatus.InTransit.ToString());
        return rows.Select(ToShipment).ToList();
    }

    public async Task CancelAsync(Guid id)
    {
        var shipment = await RequireAsync(id);
        if (shipment.Status != ShipmentStatus.Booked)
        {
            throw new InvalidOperationException($"Shipment {shipment.TrackingNumber} can no longer be cancelled.");
        }

        await _repository.UpdateStatusAsync(id, ShipmentStatus.Cancelled.ToString());
    }

    public async Task<Invoice> MarkDeliveredAsync(Guid id)
    {
        var shipment = await RequireAsync(id);
        if (shipment.Status == ShipmentStatus.Cancelled)
        {
            throw new InvalidOperationException($"Shipment {shipment.TrackingNumber} was cancelled.");
        }

        shipment.Status = ShipmentStatus.Delivered;
        await _repository.UpdateStatusAsync(id, ShipmentStatus.Delivered.ToString());
        _bus.Publish("shipment.delivered", new { id = shipment.Id });
        return await _billing.IssueInvoiceAsync(shipment);
    }

    public async Task<TrackingAnswer> TrackAsync(Guid id)
    {
        var shipment = await RequireAsync(id);
        var response = await _http.PostAsJsonAsync("http://worker:8081/track", new { shipmentId = shipment.Id });
        response.EnsureSuccessStatusCode();
        var answer = await response.Content.ReadFromJsonAsync<TrackingAnswer>();
        return answer ?? new TrackingAnswer(shipment.Status.ToString(), "unknown");
    }

    public async Task ApplyTrackingUpdateAsync(Guid id, TrackingUpdate update)
    {
        var shipment = await RequireAsync(id);
        if (update.Status == "in_transit" && shipment.Status == ShipmentStatus.Booked)
        {
            await _repository.UpdateStatusAsync(id, ShipmentStatus.InTransit.ToString());
        }

        _bus.Publish("shipment.tracked", new { id, update.Status, update.Location });
    }

    public async Task ReweighAsync(Guid id, decimal weightKg)
    {
        if (weightKg <= 0 || weightKg > MaxWeightKg)
        {
            throw new ArgumentException($"A measured weight must be between 0 and {MaxWeightKg} kg.");
        }

        var shipment = await RequireAsync(id);
        await shipment.Parcel.ReweighAsync(weightKg, _database);
        _bus.Publish("shipment.reweighed", new { id, weightKg });
    }

    public string LabelText(Shipment shipment)
    {
        var lines = new[]
        {
            shipment.TrackingNumber,
            Helpers.CleanText(shipment.Recipient),
            Helpers.CleanText(shipment.Address),
            $"Booked {Helpers.FormatDate(shipment.BookedAt)}",
        };
        return string.Join("\n", lines);
    }

    private static void Validate(BookShipmentRequest request)
    {
        if (string.IsNullOrWhiteSpace(request.Recipient))
        {
            throw new ArgumentException("A recipient is required.");
        }

        if (string.IsNullOrWhiteSpace(request.Address))
        {
            throw new ArgumentException("An address is required.");
        }

        if (request.WeightKg <= 0 || request.WeightKg > MaxWeightKg)
        {
            throw new ArgumentException($"Weight must be between 0 and {MaxWeightKg} kg.");
        }

        if (request.LengthCm > MaxSideCm || request.WidthCm > MaxSideCm || request.HeightCm > MaxSideCm)
        {
            throw new ArgumentException($"No side of a parcel may be over {MaxSideCm} cm.");
        }
    }

    private async Task<Shipment> RequireAsync(Guid id)
    {
        return await GetAsync(id) ?? throw new KeyNotFoundException($"No shipment {id}.");
    }

    private static string NewTrackingNumber()
    {
        var stamp = DateTime.UtcNow.ToString("yyMMddHHmm");
        var suffix = Random.Shared.Next(1000, 9999);
        return $"ACME{stamp}{suffix}";
    }

    private static ShipmentRow ToRow(Shipment shipment)
    {
        return new ShipmentRow(
            shipment.Id,
            shipment.TrackingNumber,
            shipment.Sender,
            shipment.Recipient,
            shipment.Address,
            shipment.Parcel,
            shipment.Price,
            shipment.Status.ToString(),
            shipment.BookedAt);
    }

    private static Shipment ToShipment(ShipmentRow row)
    {
        return new Shipment
        {
            Id = row.Id,
            TrackingNumber = row.TrackingNumber,
            Sender = row.Sender,
            Recipient = row.Recipient,
            Address = row.Address,
            Parcel = row.Parcel,
            Price = row.Price,
            Status = Enum.Parse<ShipmentStatus>(row.Status),
            BookedAt = row.BookedAt,
        };
    }
}
