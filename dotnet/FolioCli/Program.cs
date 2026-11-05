// FolioCli: batch stdin-JSON -> stdout-JSON driver for FolioCore.
//
// Protocol (stdin):
//   {"ops": [
//     {"id": "x1", "op": "xirr", "flows": [{"d": "2021-01-01", "a": -1000.0}, ...]},
//     {"id": "t1", "op": "twr",  "valuations": [{"d": "...", "v": 1000.0, "f": 0.0}, ...]},
//     {"id": "b1", "op": "benchmark",
//      "portfolio": [{"d": "...", "v": 1000.0}, ...],
//      "bench":     [{"d": "...", "v": 400.0}, ...]}
//   ]}
//
// Response (stdout):
//   {"engine": "dotnet", "version": "1.0.0", "results": [
//     {"id": "x1", "ok": true, "value": 0.1},
//     {"id": "e1", "ok": false, "error": "..."} ]}
//
// Per-operation failures are reported in-band (ok:false) with the SAME error
// message text as the Python implementation, so the caller can raise the
// equivalent exception. A malformed top-level request exits non-zero with a
// diagnostic on stderr — the Python wrapper treats that as "native failed"
// and falls back to the pure-Python implementation.

using System.Text;
using System.Text.Json;
using FolioCore;

const string Version = "1.0.0";

JsonDocument doc;
try
{
    using var stdin = Console.OpenStandardInput();
    doc = await JsonDocument.ParseAsync(stdin);
}
catch (JsonException e)
{
    Console.Error.WriteLine($"invalid request JSON: {e.Message}");
    return 1;
}

var results = new List<object?>();
if (doc.RootElement.TryGetProperty("ops", out var ops) &&
    ops.ValueKind == JsonValueKind.Array)
{
    foreach (var opEl in ops.EnumerateArray())
        results.Add(RunOp(opEl));
}

var outOpts = new JsonWriterOptions { SkipValidation = false };
using var buf = new MemoryStream();
await using (var w = new Utf8JsonWriter(buf, outOpts))
{
    w.WriteStartObject();
    w.WriteString("engine", "dotnet");
    w.WriteString("version", Version);
    w.WritePropertyName("results");
    w.WriteStartArray();
    foreach (var r in results)
        WriteResult(w, (Dictionary<string, object?>)r!);
    w.WriteEndArray();
    w.WriteEndObject();
}
Console.OpenStandardOutput().Write(buf.ToArray());
return 0;

static Dictionary<string, object?> RunOp(JsonElement opEl)
{
    var res = new Dictionary<string, object?>();
    string id = opEl.TryGetProperty("id", out var idEl) ? idEl.GetString() ?? "" : "";
    res["id"] = id;
    try
    {
        string opName = opEl.TryGetProperty("op", out var opProp)
            ? opProp.GetString() ?? ""
            : "";
        switch (opName)
        {
            case "xirr":
            {
                var flows = ReadCashFlows(opEl, "flows");
                double lo = OptDouble(opEl, "lo", -0.9999);
                double hi = OptDouble(opEl, "hi", 10.0);
                double tol = OptDouble(opEl, "tol", 1e-10);
                int maxIter = (int)OptDouble(opEl, "max_iter", 200);
                res["ok"] = true;
                res["value"] = FinanceMath.Xirr(flows, lo, hi, tol, maxIter);
                break;
            }
            case "twr":
            {
                var pts = ReadValuations(opEl, "valuations");
                res["ok"] = true;
                res["value"] = FinanceMath.Twr(pts);
                break;
            }
            case "benchmark":
            {
                var port = ReadSeries(opEl, "portfolio");
                var bench = ReadSeries(opEl, "bench");
                var points = FinanceMath.NormalizedBenchmark(port, bench);
                var arr = new List<Dictionary<string, object?>>();
                foreach (var p in points)
                {
                    var row = new Dictionary<string, object?>
                    {
                        ["d"] = p.Date.ToString("yyyy-MM-dd"),
                        ["portfolio"] = p.Portfolio,
                    };
                    if (p.Benchmark is double bv)
                        row["benchmark"] = bv;
                    arr.Add(row);
                }
                res["ok"] = true;
                res["points"] = arr;
                break;
            }
            default:
                res["ok"] = false;
                res["error"] = $"unknown op: {opName}";
                break;
        }
    }
    catch (FinanceMathException e)
    {
        res["ok"] = false;
        res["error"] = e.Message;
    }
    catch (Exception e)
    {
        res["ok"] = false;
        res["error"] = $"internal error: {e.Message}";
    }
    return res;
}

static void WriteResult(Utf8JsonWriter w, Dictionary<string, object?> res)
{
    w.WriteStartObject();
    w.WriteString("id", (string?)res.GetValueOrDefault("id") ?? "");
    w.WriteBoolean("ok", res.GetValueOrDefault("ok") is true);
    if (res.TryGetValue("value", out var v) && v is double dv)
        w.WriteNumber("value", dv);
    if (res.TryGetValue("points", out var pts) && pts is List<Dictionary<string, object?>> rows)
    {
        w.WritePropertyName("points");
        w.WriteStartArray();
        foreach (var row in rows)
        {
            w.WriteStartObject();
            w.WriteString("d", (string)row["d"]!);
            w.WriteNumber("portfolio", (double)row["portfolio"]!);
            if (row.TryGetValue("benchmark", out var b) && b is double bb)
                w.WriteNumber("benchmark", bb);
            w.WriteEndObject();
        }
        w.WriteEndArray();
    }
    if (res.TryGetValue("error", out var err) && err is string es)
        w.WriteString("error", es);
    w.WriteEndObject();
}

static List<CashFlow> ReadCashFlows(JsonElement opEl, string prop)
{
    var flows = new List<CashFlow>();
    if (opEl.TryGetProperty(prop, out var arr) && arr.ValueKind == JsonValueKind.Array)
        foreach (var e in arr.EnumerateArray())
            flows.Add(new CashFlow(
                FinanceMath.ParseDate(e.GetProperty("d").GetString()!),
                e.GetProperty("a").GetDouble()));
    return flows;
}

static List<Valuation> ReadValuations(JsonElement opEl, string prop)
{
    var pts = new List<Valuation>();
    if (opEl.TryGetProperty(prop, out var arr) && arr.ValueKind == JsonValueKind.Array)
        foreach (var e in arr.EnumerateArray())
            pts.Add(new Valuation(
                FinanceMath.ParseDate(e.GetProperty("d").GetString()!),
                e.GetProperty("v").GetDouble(),
                e.TryGetProperty("f", out var f) ? f.GetDouble() : 0.0));
    return pts;
}

static List<SeriesPoint> ReadSeries(JsonElement opEl, string prop)
{
    var pts = new List<SeriesPoint>();
    if (opEl.TryGetProperty(prop, out var arr) && arr.ValueKind == JsonValueKind.Array)
        foreach (var e in arr.EnumerateArray())
            pts.Add(new SeriesPoint(
                FinanceMath.ParseDate(e.GetProperty("d").GetString()!),
                e.GetProperty("v").GetDouble()));
    return pts;
}

static double OptDouble(JsonElement opEl, string prop, double def)
    => opEl.TryGetProperty(prop, out var e) ? e.GetDouble() : def;
