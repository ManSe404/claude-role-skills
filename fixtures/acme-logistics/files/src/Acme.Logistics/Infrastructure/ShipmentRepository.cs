using Acme.Logistics.Common;
using Acme.Logistics.Domain;

namespace Acme.Logistics.Infrastructure;

public record ShipmentRow(
    Guid Id,
    string TrackingNumber,
    string Sender,
    string Recipient,
    string Address,
    Parcel Parcel,
    Money Price,
    string Status,
    DateTime BookedAt);

public class ShipmentRepository
{
    private const string SelectShipment =
        "SELECT s.id, s.tracking_number, s.sender, s.recipient, s.address, s.price, s.status, s.booked_at, " +
        "p.id, p.weight_kg, p.length_cm, p.width_cm, p.height_cm " +
        "FROM shipments s JOIN parcels p ON p.id = s.parcel_id";

    private readonly Database _database;

    public ShipmentRepository(Database database)
    {
        _database = database;
    }

    public Task InsertAsync(ShipmentRow row)
    {
        return _database.ExecuteAsync(
            "INSERT INTO shipments (id, tracking_number, sender, recipient, address, parcel_id, price, status, booked_at) " +
            "VALUES (@Id, @TrackingNumber, @Sender, @Recipient, @Address, @ParcelId, @Price, @Status, @BookedAt)",
            new
            {
                row.Id,
                row.TrackingNumber,
                row.Sender,
                row.Recipient,
                row.Address,
                ParcelId = row.Parcel.Id,
                Price = row.Price.Amount,
                row.Status,
                row.BookedAt,
            });
    }

    public Task<ShipmentRow?> FindAsync(Guid id)
    {
        return _database.QuerySingleAsync<ShipmentRow>(SelectShipment + " WHERE s.id = @id", new { id });
    }

    public Task<IReadOnlyList<ShipmentRow>> ListByRecipientAsync(string recipient)
    {
        var cleaned = Helpers.CleanText(recipient);
        return _database.QueryAsync<ShipmentRow>(SelectShipment + " WHERE s.recipient = @cleaned", new { cleaned });
    }

    public Task<IReadOnlyList<ShipmentRow>> ListByStatusAsync(string status)
    {
        return _database.QueryAsync<ShipmentRow>(SelectShipment + " WHERE s.status = @status", new { status });
    }

    public Task UpdateStatusAsync(Guid id, string status)
    {
        return _database.ExecuteAsync("UPDATE shipments SET status = @status WHERE id = @id", new { id, status });
    }
}
