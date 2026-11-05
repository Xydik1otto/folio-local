// FolioCore: computationally critical financial math, ported 1:1 from
// backend/math_finance.py (XIRR Newton + bisection, ACT/365; TWR chain of
// sub-periods) and the benchmark-series normalization from
// backend/main.py::portfolio_benchmark. Sign conventions and error messages
// are kept identical so the Python fallback and this native core are
// interchangeable bit-for-bit (within float tolerance).
//
// Sign convention for XIRR (same as Python):
//   negative = money paid INTO the portfolio (deposit/buy),
//   positive = money received OUT of the portfolio (withdrawal, final value).

using System.Globalization;

namespace FolioCore;

/// <summary>Mirrors Python's ValueError from backend/math_finance.py.</summary>
public class FinanceMathException(string message) : Exception(message);

public readonly record struct CashFlow(DateTime Date, double Amount);

public readonly record struct Valuation(DateTime Date, double Value, double ExternalFlow);

public readonly record struct SeriesPoint(DateTime Date, double Value);

public sealed record BenchmarkPoint(DateTime Date, double Portfolio, double? Benchmark);

public static class FinanceMath
{
    /// <summary>ACT/365 year fraction, same convention as Excel's XIRR.</summary>
    public static double YearFraction(DateTime d0, DateTime d1) =>
        (d1.Date - d0.Date).Days / 365.0;

    /// <summary>Net present value of cashflows discounted at an annual rate, ACT/365.</summary>
    public static double Npv(IReadOnlyList<CashFlow> cashflows, double rate)
    {
        if (cashflows.Count == 0)
            return 0.0;
        var t0 = cashflows[0].Date;
        foreach (var cf in cashflows)
            if (cf.Date < t0)
                t0 = cf.Date;
        double sum = 0.0;
        foreach (var cf in cashflows)                 // same order as Python's sum()
            sum += cf.Amount / Math.Pow(1.0 + rate, YearFraction(t0, cf.Date));
        return sum;
    }

    /// <summary>
    /// Annualised money-weighted return via Newton-Raphson with a bisection fallback.
    /// Raises <see cref="FinanceMathException"/> when no sign change exists in
    /// [lo, hi] (no solution) or the cash flows are degenerate (all same sign /
    /// empty / single flow) — same messages as the Python port.
    /// </summary>
    public static double Xirr(IReadOnlyList<CashFlow> cashflows,
                              double lo = -0.9999, double hi = 10.0,
                              double tol = 1e-10, int maxIter = 200)
    {
        var flows = new List<CashFlow>();
        foreach (var cf in cashflows)
            if (cf.Amount != 0.0)
                flows.Add(cf);
        if (flows.Count < 2)
            throw new FinanceMathException("XIRR needs at least two non-zero cash flows");
        bool hasNeg = false, hasPos = false;
        foreach (var cf in flows)
        {
            if (cf.Amount < 0) hasNeg = true;
            if (cf.Amount > 0) hasPos = true;
        }
        if (!(hasNeg && hasPos))
            throw new FinanceMathException(
                "XIRR needs at least one negative and one positive cash flow");

        double NpvOf(double r) => Npv(flows, r);

        double Df(double r)
        {
            var t0 = flows[0].Date;
            foreach (var cf in flows)
                if (cf.Date < t0)
                    t0 = cf.Date;
            // d/dr of a/(1+r)^t = -t*a/(1+r)^(t+1)
            double sum = 0.0;
            foreach (var cf in flows)
                sum += -YearFraction(t0, cf.Date) * cf.Amount
                       / Math.Pow(1.0 + r, YearFraction(t0, cf.Date) + 1);
            return sum;
        }

        double a = lo, b = hi;
        double fa = NpvOf(a), fb = NpvOf(b);
        if (fa * fb > 0)
            throw new FinanceMathException("no XIRR solution in search bracket");

        // Try Newton first from the midpoint; fall back to guaranteed bisection.
        double r = (a + b) / 2.0;
        for (int i = 0; i < maxIter; i++)
        {
            double fr = NpvOf(r);
            if (Math.Abs(fr) < tol)
                return r;
            double dr = Df(r);
            if (dr == 0)
                break;
            double step = fr / dr;
            double nr = r - step;
            if (!(lo < nr && nr < hi) || nr == r)
                break;
            r = nr;
        }

        // Bisection (always converges given the sign change).
        for (int i = 0; i < maxIter; i++)
        {
            double m = (a + b) / 2.0;
            double fm = NpvOf(m);
            if (Math.Abs(fm) < tol || (b - a) / 2.0 < tol)
                return m;
            if (fa * fm < 0) { b = m; fb = fm; }
            else { a = m; fa = fm; }
        }
        return (a + b) / 2.0;
    }

    /// <summary>
    /// TWR from a series of (date, portfolio_value, external_flow_at_that_date).
    /// The first entry must carry flow 0.0 (opening value). With flows occurring
    /// at the END of each sub-period i:
    ///   r_i = (V(t_i) - F_i) / V(t_{i-1}),   TWR = prod(1 + r_i) - 1
    /// </summary>
    public static double Twr(IReadOnlyList<Valuation> valuations)
    {
        var pts = new List<Valuation>(valuations);
        pts.Sort((x, y) =>
        {
            int c = x.Date.CompareTo(y.Date);
            if (c != 0) return c;
            c = x.Value.CompareTo(y.Value);
            return c != 0 ? c : x.ExternalFlow.CompareTo(y.ExternalFlow);
        });
        if (pts.Count < 2)
            throw new FinanceMathException("TWR needs at least two valuation points");
        double product = 1.0;
        for (int i = 1; i < pts.Count; i++)
        {
            var (_, vPrev, _) = pts[i - 1];
            var (d, v, flow) = pts[i];
            double baseValue = vPrev;
            if (baseValue <= 0)
                throw new FinanceMathException(
                    $"non-positive opening value on {d:yyyy-MM-dd}");
            product *= (v - flow) / baseValue;
        }
        return product - 1.0;
    }

    /// <summary>
    /// Normalized benchmark series, ported from main.py::portfolio_benchmark:
    /// both series are indexed to 100 at the first portfolio date; the
    /// benchmark is a step function (last known close on or before each date).
    /// Returns RAW normalized values — rounding to 2 decimals is presentation
    /// and stays on the Python side (round-half-even parity).
    /// </summary>
    public static IReadOnlyList<BenchmarkPoint> NormalizedBenchmark(
        IReadOnlyList<SeriesPoint> portfolio, IReadOnlyList<SeriesPoint> benchmark)
    {
        var port = new List<SeriesPoint>(portfolio);
        port.Sort((x, y) => x.Date.CompareTo(y.Date));
        var bench = new List<SeriesPoint>(benchmark);
        bench.Sort((x, y) => x.Date.CompareTo(y.Date));
        if (port.Count == 0)
            throw new FinanceMathException("no portfolio valuation in range");

        double BenchAt(DateTime day)
        {
            double? last = null;
            foreach (var p in bench)
            {
                if (p.Date <= day) last = p.Value;
                else break;
            }
            return last ?? double.NaN;
        }

        var (d0, p0) = port[0];
        double b0 = BenchAt(d0);
        if (double.IsNaN(b0) || p0 <= 1e-9)
            throw new FinanceMathException("cannot normalize benchmark series");

        var points = new List<BenchmarkPoint>(port.Count);
        foreach (var (d, total) in port)
        {
            double b = BenchAt(d);
            points.Add(new BenchmarkPoint(d, 100.0 * total / p0,
                double.IsNaN(b) ? null : 100.0 * b / b0));
        }
        return points;
    }

    /// <summary>Parses an ISO YYYY-MM-DD date (the only wire date format).</summary>
    public static DateTime ParseDate(string s) =>
        DateTime.TryParseExact(s, "yyyy-MM-dd", CultureInfo.InvariantCulture,
            DateTimeStyles.None, out var d)
            ? d
            : throw new FinanceMathException($"invalid date: {s}");
}
