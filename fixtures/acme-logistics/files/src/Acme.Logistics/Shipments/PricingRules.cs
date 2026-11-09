using Acme.Logistics.Domain;

namespace Acme.Logistics.Shipments;

public static class PricingRules
{
    private const decimal BasePrice = 250m;
    private const decimal PricePerKg = 40m;
    private const decimal HeavyThresholdKg = 20m;
    private const decimal HeavySurcharge = 1.30m;
    private const decimal ExpressMultiplier = 1.50m;
    private const decimal RemoteZoneFee = 180m;
    private const decimal FuelSurcharge = 1.06m;
    private const decimal VolumetricDivisor = 5000m;

    public static Money Quote(Parcel parcel, bool express, bool remoteZone)
    {
        var volumetricKg = parcel.VolumeCm3 / VolumetricDivisor;
        var billableKg = Math.Max(parcel.WeightKg, volumetricKg);
        var price = BasePrice + billableKg * PricePerKg;
        if (billableKg > HeavyThresholdKg)
        {
            price *= HeavySurcharge;
        }

        if (express)
        {
            price *= ExpressMultiplier;
        }

        if (remoteZone)
        {
            price += RemoteZoneFee;
        }

        price *= FuelSurcharge;
        return Money.Rsd(price);
    }
}
