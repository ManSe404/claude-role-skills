using Acme.Logistics.Common;
using Acme.Logistics.Shipments;
using Microsoft.AspNetCore.Mvc;

namespace Acme.Api.Controllers;

public record ReweighRequest(decimal WeightKg);

[ApiController]
[Route("api/shipments")]
public class ShipmentsController : ControllerBase
{
    private readonly ShipmentService _shipments;

    public ShipmentsController(ShipmentService shipments)
    {
        _shipments = shipments;
    }

    [HttpGet]
    public async Task<IActionResult> List(string recipient)
    {
        var shipments = await _shipments.ListForRecipientAsync(recipient);
        return Ok(shipments.Select(ToResponse));
    }

    [HttpGet("{id:guid}")]
    public async Task<IActionResult> Get(Guid id)
    {
        var shipment = await _shipments.GetAsync(id);
        return shipment is null ? NotFound() : Ok(ToResponse(shipment));
    }

    [HttpPost]
    public async Task<IActionResult> Book(BookShipmentRequest request)
    {
        var shipment = await _shipments.BookAsync(request);
        return CreatedAtAction(nameof(Get), new { id = shipment.Id }, ToResponse(shipment));
    }

    [HttpPost("{id:guid}/cancel")]
    public async Task<IActionResult> Cancel(Guid id)
    {
        await _shipments.CancelAsync(id);
        return NoContent();
    }

    [HttpPost("{id:guid}/delivered")]
    public async Task<IActionResult> Delivered(Guid id)
    {
        var invoice = await _shipments.MarkDeliveredAsync(id);
        return Ok(new { invoice.Number, Total = invoice.Total.Amount });
    }

    [HttpGet("{id:guid}/tracking")]
    public async Task<IActionResult> Tracking(Guid id)
    {
        return Ok(await _shipments.TrackAsync(id));
    }

    [HttpPost("{id:guid}/tracking")]
    public async Task<IActionResult> ReportTracking(Guid id, TrackingUpdate update)
    {
        await _shipments.ApplyTrackingUpdateAsync(id, update);
        return NoContent();
    }

    [HttpPost("{id:guid}/reweigh")]
    public async Task<IActionResult> Reweigh(Guid id, ReweighRequest request)
    {
        await _shipments.ReweighAsync(id, request.WeightKg);
        return NoContent();
    }

    private static object ToResponse(Shipment shipment)
    {
        return new
        {
            shipment.Id,
            shipment.TrackingNumber,
            shipment.Recipient,
            Status = shipment.Status.ToString(),
            Price = shipment.Price.Amount,
            Booked = Helpers.FormatDate(shipment.BookedAt),
        };
    }
}
