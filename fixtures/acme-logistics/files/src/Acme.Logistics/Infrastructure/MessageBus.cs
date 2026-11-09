using System.Text.Json;
using Acme.Logistics.Common;
using RabbitMQ.Client;

namespace Acme.Logistics.Infrastructure;

public class MessageBus
{
    private const string Exchange = "acme.events";

    private readonly string _url;

    public MessageBus(string url)
    {
        _url = url;
    }

    public void Publish(string routingKey, object message)
    {
        var factory = new ConnectionFactory { Uri = new Uri(_url) };
        using var connection = factory.CreateConnection();
        using var channel = connection.CreateModel();
        channel.ExchangeDeclare(Exchange, ExchangeType.Topic, durable: true);
        var body = JsonSerializer.SerializeToUtf8Bytes(message);
        Helpers.Retry(() => channel.BasicPublish(Exchange, routingKey, null, body));
    }
}
