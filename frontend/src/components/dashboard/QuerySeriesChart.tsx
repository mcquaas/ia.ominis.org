'use client';

import { useEffect, useId, useMemo, useState } from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { QuerySeries } from '@/types/auth';

type RangeKey = '7d' | '30d' | '12w' | '12m';

const RANGE_OPTIONS: { id: RangeKey; label: string; field: keyof QuerySeries }[] = [
  { id: '7d', label: '7 días', field: 'last7Days' },
  { id: '30d', label: '30 días', field: 'last30Days' },
  { id: '12w', label: '12 semanas', field: 'last12Weeks' },
  { id: '12m', label: '12 meses', field: 'last12Months' },
];

function formatXLabel(bucketStart: string, range: RangeKey): string {
  const d = new Date(bucketStart);
  if (Number.isNaN(d.getTime())) return bucketStart;
  if (range === '7d') {
    return d.toLocaleDateString('es-MX', { weekday: 'short', day: 'numeric' });
  }
  if (range === '30d') {
    return d.toLocaleDateString('es-MX', { day: 'numeric', month: 'short' });
  }
  if (range === '12w') {
    return d.toLocaleDateString('es-MX', { day: 'numeric', month: 'short' });
  }
  return d.toLocaleDateString('es-MX', { month: 'short', year: '2-digit' });
}

export function QuerySeriesChart({ data }: { data: QuerySeries }) {
  const [range, setRange] = useState<RangeKey>('7d');
  const [mounted, setMounted] = useState(false);
  const gradId = useId().replace(/:/g, '');

  useEffect(() => {
    setMounted(true);
  }, []);

  const chartData = useMemo(() => {
    const field = RANGE_OPTIONS.find((o) => o.id === range)!.field;
    const points = data[field] ?? [];
    return points.map((p) => ({
      bucketStart: p.bucketStart,
      count: p.count,
      label: formatXLabel(p.bucketStart, range),
    }));
  }, [data, range]);

  const total = useMemo(() => chartData.reduce((s, r) => s + r.count, 0), [chartData]);

  return (
    <div className="bg-white/5 backdrop-blur-md border border-white/10 rounded-2xl p-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
        <div>
          <h3 className="text-sm font-semibold text-white">Consultas en el tiempo</h3>
          <p className="text-[11px] text-gray-500 mt-0.5">
            Totales por día, semana o mes (UTC) · suma en vista:{' '}
            <span className="text-cyan-400/90 font-medium">{total}</span>
          </p>
        </div>
        <div className="flex flex-wrap gap-1">
          {RANGE_OPTIONS.map((o) => (
            <button
              key={o.id}
              type="button"
              onClick={() => setRange(o.id)}
              className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
                range === o.id
                  ? 'bg-cyan-500/20 border-cyan-500/40 text-cyan-200'
                  : 'bg-white/5 border-white/10 text-gray-400 hover:text-white hover:bg-white/10'
              }`}
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>
      <div className="h-[280px] w-full min-w-0">
        {!mounted ? (
          <div className="h-full w-full rounded-xl bg-white/[0.03] animate-pulse" aria-hidden />
        ) : (
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id={`qfill-${gradId}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#22d3ee" stopOpacity={0.35} />
                <stop offset="95%" stopColor="#22d3ee" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.07)" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fill: '#9ca3af', fontSize: 10 }}
              minTickGap={range === '30d' ? 8 : 16}
              interval="preserveStartEnd"
            />
            <YAxis tick={{ fill: '#9ca3af', fontSize: 10 }} width={40} allowDecimals={false} />
            <Tooltip
              cursor={{ stroke: 'rgba(34, 211, 238, 0.35)' }}
              content={({ active, payload }) => {
                if (!active || !payload?.[0]) return null;
                const row = payload[0].payload as { bucketStart: string; count: number };
                return (
                  <div className="rounded-lg border border-white/10 bg-[#0f172a] px-3 py-2 text-xs text-gray-200 shadow-xl">
                    <div className="text-[10px] text-gray-400">
                      {new Date(row.bucketStart).toLocaleString('es-MX', { dateStyle: 'medium' })}
                    </div>
                    <div className="text-cyan-300 font-semibold mt-0.5">{row.count} consultas</div>
                  </div>
                );
              }}
            />
            <Area
              type="monotone"
              dataKey="count"
              stroke="#22d3ee"
              strokeWidth={2}
              fillOpacity={1}
              fill={`url(#qfill-${gradId})`}
            />
          </AreaChart>
        </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
