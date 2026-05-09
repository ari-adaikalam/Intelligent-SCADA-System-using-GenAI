using Microsoft.Data.SqlClient;
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
            _connectionString = configuration.GetConnectionString("SwatDatabase") 
                ?? throw new InvalidOperationException("Database connection string not found");
            _logger = logger;
        }

        public async Task<RawPlantData?> GetLatestDataAsync()
        {
            try
            {
                using var connection = new SqlConnection(_connectionString);
                var sql = @"
                    SELECT TOP 1
                        id AS Id,
                        ts AS Ts,
                        plant_id AS PlantId,
                        payload_json AS PayloadJson
                    FROM dbo.raw_plant_data
                    ORDER BY id DESC";

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
                using var connection = new SqlConnection(_connectionString);
                var sql = $@"
                    SELECT TOP {n}
                        id AS Id,
                        ts AS Ts,
                        plant_id AS PlantId,
                        payload_json AS PayloadJson
                    FROM dbo.raw_plant_data
                    ORDER BY id DESC";

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
                using var connection = new SqlConnection(_connectionString);
                
                string sql;
                object parameters;

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
                        ORDER BY ts ASC";
                    parameters = new { StartTime = startTime, EndTime = endTime, PlantId = plantId };
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
                        ORDER BY ts ASC";
                    parameters = new { StartTime = startTime, EndTime = endTime };
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
                using var connection = new SqlConnection(_connectionString);
                
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
                using var connection = new SqlConnection(_connectionString);
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
