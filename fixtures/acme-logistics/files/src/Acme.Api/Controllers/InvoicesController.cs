using Acme.Logistics.Billing;
using Acme.Logistics.Common;
using Microsoft.AspNetCore.Mvc;

namespace Acme.Api.Controllers;

[ApiController]
[Route("api/invoices")]
public class InvoicesController : ControllerBase
{
    private readonly BillingService _billing;

    public InvoicesController(BillingService billing)
    {
        _billing = billing;
    }

    [HttpGet]
    public async Task<IActionResult> List(Guid shipmentId)
    {
        var invoices = await _billing.ListForShipmentAsync(shipmentId);
        return Ok(invoices.Select(invoice => new
        {
            invoice.Number,
            invoice.ShipmentId,
            Total = invoice.Total.Amount,
            Issued = Helpers.FormatDate(invoice.IssuedAt),
        }));
    }

    [HttpPost("{number}/credit")]
    public async Task<IActionResult> Credit(string number)
    {
        await _billing.CreditAsync(number);
        return NoContent();
    }
}
