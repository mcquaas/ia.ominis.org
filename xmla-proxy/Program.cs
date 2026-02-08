/*
 * XMLA Proxy — Lightweight .NET 8 REST API for querying SSAS cubes.
 *
 * This microservice bridges the gap between the Python backend (Linux) and
 * SQL Server Analysis Services (SSAS) which requires ADOMD.NET for TCP connections.
 *
 * Runs on port 5001 alongside the FastAPI backend (port 8000).
 * Only accepts connections from localhost by default.
 *
 * Endpoints:
 *   POST /mdx              — Execute an MDX query
 *   POST /discover          — Discover cubes, dimensions, measures
 *   GET  /health            — Health check
 */

using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.AnalysisServices.AdomdClient;
using System.Data;
using System.Linq;
using System.Text.Json;

var builder = WebApplication.CreateBuilder(args);

// Listen on all interfaces on port 5001
// When running on the same machine, use http://127.0.0.1:5001
// When running on a separate Windows instance, accept connections from the backend
var listenUrl = Environment.GetEnvironmentVariable("ASPNETCORE_URLS") ?? "http://0.0.0.0:5001";
builder.WebHost.UseUrls(listenUrl);

builder.Services.AddCors(options =>
{
    options.AddDefaultPolicy(policy => policy.AllowAnyOrigin().AllowAnyMethod().AllowAnyHeader());
});

var app = builder.Build();
app.UseCors();

// --- Health check ---
app.MapGet("/health", () => Results.Ok(new { status = "healthy", service = "xmla-proxy" }));

// --- Execute MDX query ---
app.MapPost("/mdx", async (HttpContext context) =>
{
    var request = await context.Request.ReadFromJsonAsync<MdxRequest>();
    if (request == null || string.IsNullOrWhiteSpace(request.Query))
    {
        return Results.BadRequest(new { error = "Missing 'query' field" });
    }

    var connectionString = BuildConnectionString(request);

    try
    {
        using var connection = new AdomdConnection(connectionString);
        connection.Open();

        using var command = new AdomdCommand(request.Query, connection);
        command.CommandTimeout = request.Timeout > 0 ? request.Timeout : 120;

        var result = new MdxResult();

        // Try CellSet for multidimensional results
        try
        {
            var cellSet = command.ExecuteCellSet();
            result = ParseCellSet(cellSet);
        }
        catch
        {
            // Fall back to DataReader for tabular results
            using var reader = command.ExecuteReader();
            result = ParseDataReader(reader);
        }

        connection.Close();
        return Results.Ok(result);
    }
    catch (AdomdConnectionException ex)
    {
        return Results.Json(new { success = false, error = $"Connection failed: {ex.Message}" }, statusCode: 502);
    }
    catch (AdomdErrorResponseException ex)
    {
        return Results.Json(new { success = false, error = $"MDX error: {ex.Message}" }, statusCode: 400);
    }
    catch (Exception ex)
    {
        return Results.Json(new { success = false, error = ex.Message }, statusCode: 500);
    }
});

// --- Discover cubes/dimensions/measures ---
app.MapPost("/discover", async (HttpContext context) =>
{
    var request = await context.Request.ReadFromJsonAsync<DiscoverRequest>();
    if (request == null)
    {
        return Results.BadRequest(new { error = "Invalid request" });
    }

    var connectionString = BuildConnectionString(new MdxRequest
    {
        Server = request.Server,
        Catalog = request.Catalog,
        Username = request.Username,
        Password = request.Password,
    });

    try
    {
        using var connection = new AdomdConnection(connectionString);
        connection.Open();

        DataSet? schemaData = null;
        switch (request.Type?.ToLower())
        {
            case "cubes":
                schemaData = connection.GetSchemaDataSet(
                    AdomdSchemaGuid.Cubes, new object[] { request.Catalog });
                break;
            case "dimensions":
                schemaData = connection.GetSchemaDataSet(
                    AdomdSchemaGuid.Dimensions,
                    new object[] { request.Catalog, null, request.CubeName });
                break;
            case "measures":
                schemaData = connection.GetSchemaDataSet(
                    AdomdSchemaGuid.Measures,
                    new object[] { request.Catalog, null, request.CubeName });
                break;
            case "hierarchies":
                schemaData = connection.GetSchemaDataSet(
                    AdomdSchemaGuid.Hierarchies,
                    new object[] { request.Catalog, null, request.CubeName });
                break;
            case "members":
                schemaData = connection.GetSchemaDataSet(
                    AdomdSchemaGuid.Members,
                    new object[] { request.Catalog, null, request.CubeName,
                                   request.DimensionName, request.HierarchyName });
                break;
            default:
                return Results.BadRequest(new { error = $"Unknown discover type: {request.Type}" });
        }

        connection.Close();

        if (schemaData == null || schemaData.Tables.Count == 0)
        {
            return Results.Ok(new { success = true, columns = Array.Empty<string>(), rows = Array.Empty<object>() });
        }

        var table = schemaData.Tables[0];
        var columns = table.Columns.Cast<DataColumn>().Select(c => c.ColumnName).ToList();
        var rows = new List<Dictionary<string, object?>>();

        foreach (DataRow row in table.Rows)
        {
            var dict = new Dictionary<string, object?>();
            foreach (var col in columns)
            {
                dict[col] = row[col] == DBNull.Value ? null : row[col];
            }
            rows.Add(dict);
        }

        return Results.Ok(new { success = true, columns, rows, row_count = rows.Count });
    }
    catch (Exception ex)
    {
        return Results.Json(new { success = false, error = ex.Message }, statusCode: 500);
    }
});

app.Run();

// --- Helper functions ---

static string BuildConnectionString(MdxRequest request)
{
    var parts = new List<string>
    {
        $"Data Source={request.Server ?? "pwidgis03.salud.gob.mx"}",
    };

    if (!string.IsNullOrWhiteSpace(request.Catalog))
        parts.Add($"Initial Catalog={request.Catalog}");

    if (!string.IsNullOrWhiteSpace(request.Username))
        parts.Add($"User ID={request.Username}");

    if (!string.IsNullOrWhiteSpace(request.Password))
        parts.Add($"Password={request.Password}");

    // Note: Do NOT add Provider=MSOLAP — that's for OLE DB connections only.
    // ADOMD.NET uses its own protocol and doesn't need a provider specification.

    return string.Join(";", parts);
}

static MdxResult ParseDataReader(AdomdDataReader reader)
{
    var result = new MdxResult { Success = true };
    var columns = new List<string>();

    for (int i = 0; i < reader.FieldCount; i++)
    {
        columns.Add(reader.GetName(i));
    }
    result.Columns = columns;

    while (reader.Read())
    {
        var row = new Dictionary<string, object?>();
        for (int i = 0; i < reader.FieldCount; i++)
        {
            row[columns[i]] = reader.IsDBNull(i) ? null : reader.GetValue(i);
        }
        result.Rows.Add(row);
    }

    result.RowCount = result.Rows.Count;
    return result;
}

static MdxResult ParseCellSet(CellSet cellSet)
{
    var result = new MdxResult { Success = true };

    if (cellSet.Axes.Count < 2)
    {
        // Single axis or scalar result
        result.Columns = new List<string> { "Value" };
        for (int i = 0; i < cellSet.Cells.Count; i++)
        {
            result.Rows.Add(new Dictionary<string, object?>
            {
                ["Value"] = cellSet.Cells[i].Value
            });
        }
        result.RowCount = result.Rows.Count;
        return result;
    }

    // Build column headers from axis 0
    var colAxis = cellSet.Axes[0];
    var rowAxis = cellSet.Axes[1];

    var colNames = new List<string>();
    foreach (Position p in colAxis.Positions)
    {
        var memberNames = new List<string>();
        foreach (Member m in p.Members) memberNames.Add(m.Caption);
        colNames.Add(string.Join(" / ", memberNames));
    }

    result.Columns = new List<string> { "Dimension" };
    result.Columns.AddRange(colNames);

    // Build rows from axis 1
    for (int r = 0; r < rowAxis.Positions.Count; r++)
    {
        var row = new Dictionary<string, object?>();
        var rowMemberNames = new List<string>();
        foreach (Member m in rowAxis.Positions[r].Members) rowMemberNames.Add(m.Caption);
        var rowLabel = string.Join(" / ", rowMemberNames);
        row["Dimension"] = rowLabel;

        for (int c = 0; c < colAxis.Positions.Count; c++)
        {
            var cellIndex = r * colAxis.Positions.Count + c;
            if (cellIndex < cellSet.Cells.Count)
            {
                row[colNames[c]] = cellSet.Cells[cellIndex].Value;
            }
        }
        result.Rows.Add(row);
    }

    result.RowCount = result.Rows.Count;
    return result;
}

// --- Request/Response models ---

record MdxRequest
{
    public string? Server { get; set; }
    public string? Catalog { get; set; }
    public string? Username { get; set; }
    public string? Password { get; set; }
    public string? Query { get; set; }
    public int Timeout { get; set; } = 120;
}

record DiscoverRequest
{
    public string? Server { get; set; }
    public string? Catalog { get; set; }
    public string? Username { get; set; }
    public string? Password { get; set; }
    public string? Type { get; set; }         // cubes, dimensions, measures, hierarchies, members
    public string? CubeName { get; set; }
    public string? DimensionName { get; set; }
    public string? HierarchyName { get; set; }
}

class MdxResult
{
    public bool Success { get; set; }
    public List<string> Columns { get; set; } = new();
    public List<Dictionary<string, object?>> Rows { get; set; } = new();
    public int RowCount { get; set; }
    public string? Error { get; set; }
}
