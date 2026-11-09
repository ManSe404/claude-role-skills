using Acme.Logistics.Billing;
using Acme.Logistics.Infrastructure;
using Acme.Logistics.Shipments;

var builder = WebApplication.CreateBuilder(args);

var databaseUrl = Environment.GetEnvironmentVariable("ACME_DATABASE_URL") ?? "";
var queueUrl = Environment.GetEnvironmentVariable("ACME_QUEUE_URL") ?? "";

builder.Services.AddControllers();
builder.Services.AddSingleton(new Database(databaseUrl));
builder.Services.AddSingleton(new MessageBus(queueUrl));
builder.Services.AddScoped<ShipmentRepository>();
builder.Services.AddScoped<BillingService>();
builder.Services.AddHttpClient<ShipmentService>();

var app = builder.Build();
app.MapControllers();
app.Run();
