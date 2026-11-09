namespace Acme.Logistics.Domain;

public readonly record struct Money(decimal Amount, string Currency)
{
    public static Money Zero => new(0m, "RSD");

    public static Money Rsd(decimal amount)
    {
        return new Money(Math.Round(amount, 2), "RSD");
    }

    public Money Add(Money other)
    {
        if (other.Currency != Currency)
        {
            throw new InvalidOperationException("Cannot add two different currencies.");
        }

        return this with { Amount = Amount + other.Amount };
    }

    public override string ToString()
    {
        return $"{Amount:0.00} {Currency}";
    }
}
