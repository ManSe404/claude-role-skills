using Dapper;
using Npgsql;

namespace Acme.Logistics.Infrastructure;

public class Database
{
    private readonly string _connectionString;

    public Database(string connectionString)
    {
        _connectionString = connectionString;
    }

    public async Task<int> ExecuteAsync(string sql, object? args = null)
    {
        await using var connection = new NpgsqlConnection(_connectionString);
        return await connection.ExecuteAsync(sql, args);
    }

    public async Task<T?> QuerySingleAsync<T>(string sql, object? args = null)
    {
        await using var connection = new NpgsqlConnection(_connectionString);
        return await connection.QuerySingleOrDefaultAsync<T>(sql, args);
    }

    public async Task<IReadOnlyList<T>> QueryAsync<T>(string sql, object? args = null)
    {
        await using var connection = new NpgsqlConnection(_connectionString);
        var rows = await connection.QueryAsync<T>(sql, args);
        return rows.ToList();
    }
}
