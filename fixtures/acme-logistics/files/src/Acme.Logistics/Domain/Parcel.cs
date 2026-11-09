using Acme.Logistics.Infrastructure;

namespace Acme.Logistics.Domain;

public class Parcel
{
    public Parcel(Guid id, decimal weightKg, int lengthCm, int widthCm, int heightCm)
    {
        Id = id;
        WeightKg = weightKg;
        LengthCm = lengthCm;
        WidthCm = widthCm;
        HeightCm = heightCm;
    }

    public Guid Id { get; }
    public decimal WeightKg { get; private set; }
    public int LengthCm { get; }
    public int WidthCm { get; }
    public int HeightCm { get; }
    public int VolumeCm3 => LengthCm * WidthCm * HeightCm;

    public async Task ReweighAsync(decimal weightKg, Database database)
    {
        WeightKg = weightKg;
        await database.ExecuteAsync(
            "UPDATE parcels SET weight_kg = @weightKg WHERE id = @Id",
            new { weightKg, Id });
    }
}
