using Npgsql;
using Dapper;
using SwatDashboard.Models;
using System.Text.Json;

namespace SwatDashboard.Services
{
    public class DatabaseService
    {
        private readonly string _connectionString;
        private readonly ILogger<DatabaseService> _logger;

        public DatabaseService(IConfiguration configuration, ILogger<DatabaseService> logger)
        {
            var connectionString = configuration.GetConnectionString("SwatDatabase");
            if (string.IsNullOrWhiteSpace(connectionString))
            {
                throw new InvalidOperationException(
                    "Database connection string not found. Set the ConnectionStrings__SwatDatabase " +
                    "environment variable (see appsettings.Example.json).");
            }
            _connectionString = connectionString;
            _logger = logger;
        }

        public async Task<RawPlantData?> GetLatestDataAsync()
        {
            try
            {
                using var connection = new NpgsqlConnection(_connectionString);
                var sql = @"
                    SELECT
                        id AS Id,
                        ts AS Ts,
                        plant_id AS PlantId,
                        payload_json AS PayloadJson
                    FROM dbo.raw_plant_data
                    ORDER BY id DESC
                    LIMIT 1";

                return await connection.QueryFirstOrDefaultAsync<RawPlantData>(sql);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error fetching latest data");
                return null;
            }
        }

        public async Task<List<RawPlantData>> GetLatestNDataAsync(int n)
        {
            try
            {
                using var connection = new NpgsqlConnection(_connectionString);
                var sql = $@"
                    SELECT
                        id AS Id,
                        ts AS Ts,
                        plant_id AS PlantId,
                        payload_json AS PayloadJson
                    FROM dbo.raw_plant_data
                    ORDER BY id DESC
                    LIMIT {n}";

                var results = await connection.QueryAsync<RawPlantData>(sql);
                return results.OrderBy(r => r.Id).ToList();
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error fetching latest N data");
                return new List<RawPlantData>();
            }
        }

        public async Task<List<RawPlantData>> GetDataRangeAsync(DateTime startTime, DateTime endTime, string? plantId = null)
        {
            try
            {
                using var connection = new NpgsqlConnection(_connectionString);
                
                string sql;
                object parameters;

                // Backstop only — high enough that no real date-range query the
                // dashboard makes will ever hit it, it just stops a crafted
                // multi-decade range from forcing an unbounded full-table pull.
                const int maxRows = 2_000_000;

                if (!string.IsNullOrEmpty(plantId) && plantId != "All")
                {
                    sql = @"
                        SELECT
                            id AS Id,
                            ts AS Ts,
                            plant_id AS PlantId,
                            payload_json AS PayloadJson
                        FROM dbo.raw_plant_data
                        WHERE ts >= @StartTime AND ts <= @EndTime
                          AND plant_id = @PlantId
                        ORDER BY ts ASC
                        LIMIT @MaxRows";
                    parameters = new { StartTime = startTime, EndTime = endTime, PlantId = plantId, MaxRows = maxRows };
                }
                else
                {
                    sql = @"
                        SELECT
                            id AS Id,
                            ts AS Ts,
                            plant_id AS PlantId,
                            payload_json AS PayloadJson
                        FROM dbo.raw_plant_data
                        WHERE ts >= @StartTime AND ts <= @EndTime
                        ORDER BY ts ASC
                        LIMIT @MaxRows";
                    parameters = new { StartTime = startTime, EndTime = endTime, MaxRows = maxRows };
                }

                var results = await connection.QueryAsync<RawPlantData>(sql, parameters);
                return results.ToList();
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error fetching data range");
                return new List<RawPlantData>();
            }
        }

        public async Task<int> GetDataCountAsync(DateTime startTime, DateTime endTime, string? plantId = null)
        {
            try
            {
                using var connection = new NpgsqlConnection(_connectionString);
                
                string sql;
                object parameters;

                if (!string.IsNullOrEmpty(plantId) && plantId != "All")
                {
                    sql = @"
                        SELECT COUNT(*) 
                        FROM dbo.raw_plant_data
                        WHERE ts >= @StartTime AND ts <= @EndTime
                          AND plant_id = @PlantId";
                    parameters = new { StartTime = startTime, EndTime = endTime, PlantId = plantId };
                }
                else
                {
                    sql = @"
                        SELECT COUNT(*) 
                        FROM dbo.raw_plant_data
                        WHERE ts >= @StartTime AND ts <= @EndTime";
                    parameters = new { StartTime = startTime, EndTime = endTime };
                }

                return await connection.ExecuteScalarAsync<int>(sql, parameters);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error getting data count");
                return 0;
            }
        }

        public async Task<List<string>> GetPlantIdsAsync()
        {
            try
            {
                using var connection = new NpgsqlConnection(_connectionString);
                var sql = "SELECT DISTINCT plant_id FROM dbo.raw_plant_data WHERE plant_id IS NOT NULL ORDER BY plant_id";
                var results = await connection.QueryAsync<string>(sql);
                return results.ToList();
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error fetching plant IDs");
                return new List<string>();
            }
        }
    }
}
