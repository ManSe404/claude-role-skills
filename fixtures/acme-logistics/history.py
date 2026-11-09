"""The git history of the acme-logistics fixture.

The files under files/ are the state after the last commit. Each commit lists the files it adds and the edits it
makes, as (path, before, after). The builder walks the list backwards, undoing each edit, to recover the state after
every commit, then replays it forwards with git.

The story: Acme Logistics, a parcel company in Novi Sad, grew a .NET API, a web app for the counters and a Python
tracking worker by hand between March and October 2026. In October two briefs arrived for what comes next. Everything
here is fictional.
"""

TAMARA = ("Tamara Brankov", "tamara.brankov@example.com")
ALEKSA = ("Aleksa Mirkov", "aleksa.mirkov@example.com")
DUNJA = ("Dunja Petrak", "dunja.petrak@example.com")

SERVICE = "src/Acme.Logistics/Shipments/ShipmentService.cs"
RULES = "src/Acme.Logistics/Shipments/PricingRules.cs"
PRICING = "web/src/app/shipments/pricing.ts"
PAGE = "web/src/app/shipments/shipments.ts"
CLIENT = "web/src/app/api/client.ts"
APP = "web/src/app/app.ts"
CONTROLLER = "src/Acme.Api/Controllers/ShipmentsController.cs"
INVOICES = "src/Acme.Api/Controllers/InvoicesController.cs"
PROGRAM = "src/Acme.Api/Program.cs"
HELPERS = "src/Acme.Logistics/Common/Helpers.cs"
BILLING = "src/Acme.Logistics/Billing/BillingService.cs"
INVOICE = "src/Acme.Logistics/Billing/Invoice.cs"
PARCEL = "src/Acme.Logistics/Domain/Parcel.cs"

COMMITS = [
    {
        "date": "2026-03-03T09:30:00+01:00",
        "author": TAMARA,
        "message": "Start the API: book, find and cancel shipments",
        "add": [
            "README.md",
            ".gitignore",
            "src/Acme.Api/Acme.Api.csproj",
            PROGRAM,
            CONTROLLER,
            "src/Acme.Logistics/Acme.Logistics.csproj",
            "src/Acme.Logistics/Shipments/Shipment.cs",
            SERVICE,
            "src/Acme.Logistics/Domain/Money.cs",
            PARCEL,
            "src/Acme.Logistics/Infrastructure/Database.cs",
            "src/Acme.Logistics/Infrastructure/ShipmentRepository.cs",
            HELPERS,
        ],
    },
    {
        "date": "2026-03-24T11:10:00+01:00",
        "author": ALEKSA,
        "message": "Web app: shipment list and booking form",
        "add": ["web/package.json", APP, PAGE, CLIENT],
        "edit": [
            ("README.md", "", "- `web/`: the web app used at the counters.\n"),
        ],
    },
    {
        "date": "2026-04-07T14:20:00+02:00",
        "author": TAMARA,
        "message": "Price a shipment by weight, in the API and on the booking form",
        "add": [RULES, PRICING],
        "edit": [
            (SERVICE, "        var price = Money.Rsd(250m);\n", "        var price = PricingRules.Quote(parcel);\n"),
            (PAGE, "", "import { quote } from './pricing';\n"),
            (PAGE, "", "    <p>Estimated price: {{ estimate() }} RSD</p>\n"),
            (PAGE, "", "  estimate(): number {\n    return quote(this.form);\n  }\n\n"),
        ],
    },
    {
        "date": "2026-04-21T10:05:00+02:00",
        "author": DUNJA,
        "message": "Invoices: model, billing service, endpoints and a web page",
        "add": [INVOICE, BILLING, INVOICES, "web/src/app/invoices/invoices.ts"],
        "edit": [
            (PROGRAM, "", "using Acme.Logistics.Billing;\n"),
            (PROGRAM, "", "builder.Services.AddScoped<BillingService>();\n"),
            (APP, "", "import { InvoicesPage } from './invoices/invoices';\n"),
            (APP, "  imports: [ShipmentsPage],\n", "  imports: [ShipmentsPage, InvoicesPage],\n"),
            (APP, "", "    <acme-invoices />\n"),
            (
                CLIENT,
                "",
                "export interface Invoice {\n  number: string;\n  shipmentId: string;\n  total: number;\n}\n\n",
            ),
            (
                CLIENT,
                "",
                "\n"
                "  invoices(shipmentId: string): Observable<Invoice[]> {\n"
                "    return this.http.get<Invoice[]>('/api/invoices', { params: { shipmentId } });\n"
                "  }\n",
            ),
            (
                "README.md",
                "- `src/Acme.Logistics/`: shipments and the code they share.\n",
                "- `src/Acme.Logistics/`: shipments, billing and the code they share.\n",
            ),
        ],
    },
    {
        "date": "2026-05-05T09:45:00+02:00",
        "author": TAMARA,
        "message": "Issue the invoice when a shipment is delivered",
        "edit": [
            (SERVICE, "", "using Acme.Logistics.Billing;\n"),
            (SERVICE, "", "    private readonly BillingService _billing;\n"),
            (
                SERVICE,
                "    public ShipmentService(ShipmentRepository repository)\n",
                "    public ShipmentService(\n"
                "        ShipmentRepository repository,\n"
                "        BillingService billing)\n",
            ),
            (SERVICE, "", "        _billing = billing;\n"),
            (
                SERVICE,
                "",
                "    public async Task<Invoice> MarkDeliveredAsync(Guid id)\n"
                "    {\n"
                "        var shipment = await RequireAsync(id);\n"
                "        if (shipment.Status == ShipmentStatus.Cancelled)\n"
                "        {\n"
                '            throw new InvalidOperationException($"Shipment {shipment.TrackingNumber} '
                'was cancelled.");\n'
                "        }\n"
                "\n"
                "        shipment.Status = ShipmentStatus.Delivered;\n"
                "        await _repository.UpdateStatusAsync(id, ShipmentStatus.Delivered.ToString());\n"
                "        return await _billing.IssueInvoiceAsync(shipment);\n"
                "    }\n"
                "\n",
            ),
            (
                CONTROLLER,
                "",
                '    [HttpPost("{id:guid}/delivered")]\n'
                "    public async Task<IActionResult> Delivered(Guid id)\n"
                "    {\n"
                "        var invoice = await _shipments.MarkDeliveredAsync(id);\n"
                "        return Ok(new { invoice.Number, Total = invoice.Total.Amount });\n"
                "    }\n"
                "\n",
            ),
        ],
    },
    {
        "date": "2026-05-19T16:30:00+02:00",
        "author": ALEKSA,
        "message": "Parcels over 20 kg cost 30 percent more, API and booking form",
        "edit": [
            (
                RULES,
                "",
                "    private const decimal HeavyThresholdKg = 20m;\n"
                "    private const decimal HeavySurcharge = 1.30m;\n",
            ),
            (
                RULES,
                "",
                "        if (billableKg > HeavyThresholdKg)\n"
                "        {\n"
                "            price *= HeavySurcharge;\n"
                "        }\n"
                "\n",
            ),
            (PRICING, "", "const HEAVY_THRESHOLD_KG = 20;\nconst HEAVY_SURCHARGE = 1.3;\n"),
            (PRICING, "", "  if (billableKg > HEAVY_THRESHOLD_KG) {\n    price *= HEAVY_SURCHARGE;\n  }\n"),
        ],
    },
    {
        "date": "2026-06-04T13:15:00+02:00",
        "author": ALEKSA,
        "message": "Tracking worker and a compose file for the whole stack",
        "add": [
            "docker-compose.yml",
            "src/Acme.Api/Dockerfile",
            "web/Dockerfile",
            "src/Acme.Logistics/Infrastructure/MessageBus.cs",
            "worker/pyproject.toml",
            "worker/Dockerfile",
            "worker/src/acme_worker/__init__.py",
            "worker/src/acme_worker/__main__.py",
            "worker/src/acme_worker/tracking.py",
            "worker/src/acme_worker/notifications.py",
            "worker/src/acme_worker/db.py",
            "worker/src/acme_worker/api_client.py",
        ],
        "edit": [
            (SERVICE, "", "public record TrackingUpdate(string Status, string Location);\n\n"),
            (SERVICE, "", "    private readonly MessageBus _bus;\n"),
            (
                SERVICE,
                "        BillingService billing)\n",
                "        BillingService billing,\n        MessageBus bus)\n",
            ),
            (SERVICE, "", "        _bus = bus;\n"),
            (
                SERVICE,
                "",
                '        _bus.Publish("shipment.booked", new { id = shipment.Id, '
                "tracking = shipment.TrackingNumber });\n",
            ),
            (SERVICE, "", '        _bus.Publish("shipment.delivered", new { id = shipment.Id });\n'),
            (
                SERVICE,
                "",
                "    public async Task ApplyTrackingUpdateAsync(Guid id, TrackingUpdate update)\n"
                "    {\n"
                "        var shipment = await RequireAsync(id);\n"
                '        if (update.Status == "in_transit" && shipment.Status == ShipmentStatus.Booked)\n'
                "        {\n"
                "            await _repository.UpdateStatusAsync(id, ShipmentStatus.InTransit.ToString());\n"
                "        }\n"
                "\n"
                '        _bus.Publish("shipment.tracked", new { id, update.Status, update.Location });\n'
                "    }\n"
                "\n",
            ),
            (
                CONTROLLER,
                "",
                '    [HttpPost("{id:guid}/tracking")]\n'
                "    public async Task<IActionResult> ReportTracking(Guid id, TrackingUpdate update)\n"
                "    {\n"
                "        await _shipments.ApplyTrackingUpdateAsync(id, update);\n"
                "        return NoContent();\n"
                "    }\n"
                "\n",
            ),
            (PROGRAM, "", 'var queueUrl = Environment.GetEnvironmentVariable("ACME_QUEUE_URL") ?? "";\n'),
            (PROGRAM, "", "builder.Services.AddSingleton(new MessageBus(queueUrl));\n"),
            (
                HELPERS,
                "",
                "\n"
                "    public static void Retry(Action action, int attempts = 3)\n"
                "    {\n"
                "        for (var attempt = 1; ; attempt++)\n"
                "        {\n"
                "            try\n"
                "            {\n"
                "                action();\n"
                "                return;\n"
                "            }\n"
                "            catch (Exception) when (attempt < attempts)\n"
                "            {\n"
                "                Thread.Sleep(200 * attempt);\n"
                "            }\n"
                "        }\n"
                "    }\n",
            ),
            ("README.md", "", "- `worker/`: the tracking worker, which follows parcels with the carrier.\n"),
            (
                "README.md",
                "    dotnet run --project src/Acme.Api\n",
                "Publish the API once, then start everything with Docker Compose:\n"
                "\n"
                "    dotnet publish src/Acme.Api -c Release -o src/Acme.Api/publish\n"
                "    docker compose up --build\n"
                "\n"
                "The API listens on port 8080, the web app on 4200 and the tracking worker on 8081.\n",
            ),
        ],
    },
    {
        "date": "2026-06-18T10:40:00+02:00",
        "author": TAMARA,
        "message": "Ask the worker for the current position when someone opens a shipment",
        "edit": [
            (SERVICE, "", "using System.Net.Http.Json;\n"),
            (SERVICE, "", "public record TrackingAnswer(string Status, string Location);\n\n"),
            (SERVICE, "", "    private readonly HttpClient _http;\n"),
            (SERVICE, "        MessageBus bus)\n", "        MessageBus bus,\n        HttpClient http)\n"),
            (SERVICE, "", "        _http = http;\n"),
            (
                SERVICE,
                "",
                "    public async Task<TrackingAnswer> TrackAsync(Guid id)\n"
                "    {\n"
                "        var shipment = await RequireAsync(id);\n"
                '        var response = await _http.PostAsJsonAsync("http://worker:8081/track", '
                "new { shipmentId = shipment.Id });\n"
                "        response.EnsureSuccessStatusCode();\n"
                "        var answer = await response.Content.ReadFromJsonAsync<TrackingAnswer>();\n"
                '        return answer ?? new TrackingAnswer(shipment.Status.ToString(), "unknown");\n'
                "    }\n"
                "\n",
            ),
            (
                CONTROLLER,
                "",
                '    [HttpGet("{id:guid}/tracking")]\n'
                "    public async Task<IActionResult> Tracking(Guid id)\n"
                "    {\n"
                "        return Ok(await _shipments.TrackAsync(id));\n"
                "    }\n"
                "\n",
            ),
            (
                PROGRAM,
                "builder.Services.AddScoped<ShipmentService>();\n",
                "builder.Services.AddHttpClient<ShipmentService>();\n",
            ),
        ],
    },
    {
        "date": "2026-07-02T15:00:00+02:00",
        "author": TAMARA,
        "message": "Express delivery at 1.5 times the price, API and booking form",
        "edit": [
            (RULES, "", "    private const decimal ExpressMultiplier = 1.50m;\n"),
            (
                RULES,
                "    public static Money Quote(Parcel parcel)\n",
                "    public static Money Quote(Parcel parcel, bool express)\n",
            ),
            (RULES, "", "        if (express)\n        {\n            price *= ExpressMultiplier;\n        }\n\n"),
            (PRICING, "", "const EXPRESS_MULTIPLIER = 1.5;\n"),
            (PRICING, "", "  if (input.express) {\n    price *= EXPRESS_MULTIPLIER;\n  }\n"),
            (PRICING, "  weightKg: number;\n}\n", "  weightKg: number;\n  express: boolean;\n}\n"),
            (SERVICE, "    int HeightCm);\n", "    int HeightCm,\n    bool Express);\n"),
            (
                SERVICE,
                "        var price = PricingRules.Quote(parcel);\n",
                "        var price = PricingRules.Quote(parcel, request.Express);\n",
            ),
            (PAGE, "", "    express: false,\n"),
            (CLIENT, "  heightCm: number;\n}\n", "  heightCm: number;\n  express: boolean;\n}\n"),
        ],
    },
    {
        "date": "2026-07-16T11:25:00+02:00",
        "author": DUNJA,
        "message": "VAT on invoices",
        "edit": [
            (BILLING, "", "using Acme.Logistics.Common;\n"),
            (BILLING, "", "        var total = Helpers.AddVat(shipment.Price.Amount);\n"),
            (BILLING, "", "            Vat = Money.Rsd(total - shipment.Price.Amount),\n"),
            (
                BILLING,
                '            "INSERT INTO invoices (number, shipment_id, net, issued_at) " +\n'
                '            "VALUES (@Number, @ShipmentId, @Net, @IssuedAt)",\n'
                "            new { invoice.Number, invoice.ShipmentId, Net = invoice.Net.Amount, "
                "invoice.IssuedAt });\n",
                '            "INSERT INTO invoices (number, shipment_id, net, vat, issued_at) " +\n'
                '            "VALUES (@Number, @ShipmentId, @Net, @Vat, @IssuedAt)",\n'
                "            new { invoice.Number, invoice.ShipmentId, Net = invoice.Net.Amount, "
                "Vat = invoice.Vat.Amount, invoice.IssuedAt });\n",
            ),
            (
                BILLING,
                '            "SELECT number, shipment_id, net, issued_at FROM invoices '
                'WHERE shipment_id = @shipmentId",\n',
                '            "SELECT number, shipment_id, net, vat, issued_at FROM invoices '
                'WHERE shipment_id = @shipmentId",\n',
            ),
            (BILLING, "", "            Vat = Money.Rsd(row.Vat),\n"),
            (
                BILLING,
                "    private record InvoiceRow(string Number, Guid ShipmentId, decimal Net, DateTime IssuedAt);\n",
                "    private record InvoiceRow(string Number, Guid ShipmentId, decimal Net, decimal Vat, "
                "DateTime IssuedAt);\n",
            ),
            (
                INVOICE,
                "    public Money Total => Net;\n",
                "    public Money Vat { get; init; } = Money.Zero;\n    public Money Total => Net.Add(Vat);\n",
            ),
            (
                HELPERS,
                "",
                "    public static decimal AddVat(decimal net)\n"
                "    {\n"
                "        return Math.Round(net * 1.20m, 2);\n"
                "    }\n"
                "\n",
            ),
        ],
    },
    {
        "date": "2026-08-06T09:20:00+02:00",
        "author": TAMARA,
        "message": "Reweigh parcels at the depot",
        "edit": [
            (PARCEL, "", "using Acme.Logistics.Infrastructure;\n\n"),
            (PARCEL, "    public decimal WeightKg { get; }\n", "    public decimal WeightKg { get; private set; }\n"),
            (
                PARCEL,
                "",
                "\n"
                "    public async Task ReweighAsync(decimal weightKg, Database database)\n"
                "    {\n"
                "        WeightKg = weightKg;\n"
                "        await database.ExecuteAsync(\n"
                '            "UPDATE parcels SET weight_kg = @weightKg WHERE id = @Id",\n'
                "            new { weightKg, Id });\n"
                "    }\n",
            ),
            (SERVICE, "", "    private readonly Database _database;\n"),
            (SERVICE, "        HttpClient http)\n", "        HttpClient http,\n        Database database)\n"),
            (SERVICE, "", "        _database = database;\n"),
            (
                SERVICE,
                "",
                "    public async Task ReweighAsync(Guid id, decimal weightKg)\n"
                "    {\n"
                "        if (weightKg <= 0 || weightKg > MaxWeightKg)\n"
                "        {\n"
                '            throw new ArgumentException($"A measured weight must be between 0 and '
                '{MaxWeightKg} kg.");\n'
                "        }\n"
                "\n"
                "        var shipment = await RequireAsync(id);\n"
                "        await shipment.Parcel.ReweighAsync(weightKg, _database);\n"
                '        _bus.Publish("shipment.reweighed", new { id, weightKg });\n'
                "    }\n"
                "\n",
            ),
            (CONTROLLER, "", "public record ReweighRequest(decimal WeightKg);\n\n"),
            (
                CONTROLLER,
                "",
                '    [HttpPost("{id:guid}/reweigh")]\n'
                "    public async Task<IActionResult> Reweigh(Guid id, ReweighRequest request)\n"
                "    {\n"
                "        await _shipments.ReweighAsync(id, request.WeightKg);\n"
                "        return NoContent();\n"
                "    }\n"
                "\n",
            ),
        ],
    },
    {
        "date": "2026-08-20T14:50:00+02:00",
        "author": ALEKSA,
        "message": "Fee for remote zones, API and booking form",
        "edit": [
            (RULES, "", "    private const decimal RemoteZoneFee = 180m;\n"),
            (
                RULES,
                "    public static Money Quote(Parcel parcel, bool express)\n",
                "    public static Money Quote(Parcel parcel, bool express, bool remoteZone)\n",
            ),
            (RULES, "", "        if (remoteZone)\n        {\n            price += RemoteZoneFee;\n        }\n\n"),
            (PRICING, "", "const REMOTE_ZONE_FEE = 180;\n"),
            (PRICING, "", "  if (input.remoteZone) {\n    price += REMOTE_ZONE_FEE;\n  }\n"),
            (PRICING, "  express: boolean;\n}\n", "  express: boolean;\n  remoteZone: boolean;\n}\n"),
            (SERVICE, "    bool Express);\n", "    bool Express,\n    bool RemoteZone);\n"),
            (
                SERVICE,
                "        var price = PricingRules.Quote(parcel, request.Express);\n",
                "        var price = PricingRules.Quote(parcel, request.Express, request.RemoteZone);\n",
            ),
            (PAGE, "", "    remoteZone: false,\n"),
            (CLIENT, "  express: boolean;\n}\n", "  express: boolean;\n  remoteZone: boolean;\n}\n"),
        ],
    },
    {
        "date": "2026-09-03T10:30:00+02:00",
        "author": DUNJA,
        "message": "Credit notes for invoices issued in error",
        "edit": [
            (
                BILLING,
                "",
                "    public async Task CreditAsync(string number)\n"
                "    {\n"
                "        await _database.ExecuteAsync(\n"
                '            "UPDATE invoices SET credited = true WHERE number = @number",\n'
                "            new { number = Helpers.CleanText(number) });\n"
                "    }\n"
                "\n",
            ),
            (
                BILLING,
                '            "SELECT number, shipment_id, net, vat, issued_at FROM invoices '
                'WHERE shipment_id = @shipmentId",\n',
                '            "SELECT number, shipment_id, net, vat, issued_at, credited FROM invoices '
                'WHERE shipment_id = @shipmentId",\n',
            ),
            (BILLING, "", "            Credited = row.Credited,\n"),
            (
                BILLING,
                "    private record InvoiceRow(string Number, Guid ShipmentId, decimal Net, decimal Vat, "
                "DateTime IssuedAt);\n",
                "    private record InvoiceRow(string Number, Guid ShipmentId, decimal Net, decimal Vat, "
                "DateTime IssuedAt, bool Credited);\n",
            ),
            (INVOICE, "", "    public bool Credited { get; init; }\n"),
            (
                INVOICES,
                "",
                "\n"
                '    [HttpPost("{number}/credit")]\n'
                "    public async Task<IActionResult> Credit(string number)\n"
                "    {\n"
                "        await _billing.CreditAsync(number);\n"
                "        return NoContent();\n"
                "    }\n",
            ),
        ],
    },
    {
        "date": "2026-09-17T13:05:00+02:00",
        "author": TAMARA,
        "message": "Fuel surcharge of 6 percent, API and booking form",
        "edit": [
            (RULES, "", "    private const decimal FuelSurcharge = 1.06m;\n"),
            (RULES, "", "        price *= FuelSurcharge;\n"),
            (PRICING, "", "const FUEL_SURCHARGE = 1.06;\n"),
            (PRICING, "", "  price *= FUEL_SURCHARGE;\n"),
        ],
    },
    {
        "date": "2026-10-01T16:10:00+02:00",
        "author": ALEKSA,
        "message": "Volumetric weight for bulky parcels, API and booking form",
        "edit": [
            (RULES, "", "    private const decimal VolumetricDivisor = 5000m;\n"),
            (
                RULES,
                "        var billableKg = parcel.WeightKg;\n",
                "        var volumetricKg = parcel.VolumeCm3 / VolumetricDivisor;\n"
                "        var billableKg = Math.Max(parcel.WeightKg, volumetricKg);\n",
            ),
            (PARCEL, "", "    public int VolumeCm3 => LengthCm * WidthCm * HeightCm;\n"),
            (PRICING, "", "const VOLUMETRIC_DIVISOR = 5000;\n"),
            (
                PRICING,
                "  const billableKg = input.weightKg;\n",
                "  const volumetricKg = (input.lengthCm * input.widthCm * input.heightCm) / VOLUMETRIC_DIVISOR;\n"
                "  const billableKg = Math.max(input.weightKg, volumetricKg);\n",
            ),
            (
                PRICING,
                "  weightKg: number;\n  express: boolean;\n",
                "  weightKg: number;\n"
                "  lengthCm: number;\n"
                "  widthCm: number;\n"
                "  heightCm: number;\n"
                "  express: boolean;\n",
            ),
            (SERVICE, "", "    private const int MaxSideCm = 180;\n"),
            (
                SERVICE,
                "",
                "\n"
                "        if (request.LengthCm > MaxSideCm || request.WidthCm > MaxSideCm || "
                "request.HeightCm > MaxSideCm)\n"
                "        {\n"
                '            throw new ArgumentException($"No side of a parcel may be over {MaxSideCm} cm.");\n'
                "        }\n",
            ),
        ],
    },
    {
        "date": "2026-10-15T10:00:00+02:00",
        "author": TAMARA,
        "message": "Briefs: a booking app for Acme Couriers and the fleet platform",
        "add": ["docs/briefs/quick-booking.md", "docs/briefs/fleet-platform.md"],
        "edit": [
            ("README.md", "", "- `docs/briefs/`: briefs for what comes next.\n"),
        ],
    },
]
