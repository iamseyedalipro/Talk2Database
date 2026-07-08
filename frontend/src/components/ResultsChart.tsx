import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts';
import type { ExecuteResponse, WidgetViz } from '../api/types';
import { MAX_SERIES, X_KEY, buildChartData, buildPieData } from '../utils/chartData';
import { compactNumber, fullNumber, percent } from '../utils/format';
import ChartControls from './ChartControls';
import {
  AXIS_TICK,
  GRID_STROKE,
  LEGEND_STYLE,
  TOOLTIP_CONTENT_STYLE,
  TOOLTIP_ITEM_STYLE,
  TOOLTIP_LABEL_STYLE,
  seriesColor,
  tickLabel,
} from './chartTheme';

interface Props {
  result: ExecuteResponse;
  /** The full chart configuration; parents own this state. */
  viz: WidgetViz;
  /** When provided (and not hidden), the column/series controls render. */
  onVizChange?: (viz: WidgetViz) => void;
  /** Hide the controls (dashboard widgets render with a fixed config). */
  hideControls?: boolean;
  /** Chart canvas height in px (default 360). */
  height?: number;
}

function formatValue(value: unknown): string {
  return typeof value === 'number' ? fullNumber(value) : String(value ?? '');
}

/** Legend text wears the ink color; the swatch beside it carries the series color. */
function legendText(value: string) {
  return <span style={{ color: 'var(--text)' }}>{value}</span>;
}

/**
 * Renders the result set as a (multi-series) bar, horizontal bar, line, area,
 * radar, combo, pie, or scatter chart, driven entirely by the `viz` config.
 */
export default function ResultsChart({ result, viz, onVizChange, hideControls, height = 360 }: Props) {
  const { t } = useTranslation('results');
  const kind = viz.view;

  const data = useMemo(
    () => (kind === 'pie' ? { rows: [], series: [], truncatedSeries: false } : buildChartData(result, viz)),
    [result, viz, kind],
  );
  const pieData = useMemo(() => (kind === 'pie' ? buildPieData(result, viz) : []), [result, viz, kind]);
  const pieTotal = useMemo(() => pieData.reduce((sum, s) => sum + s.value, 0), [pieData]);

  if (result.columns.length === 0 || result.rows.length === 0 || kind === 'table') {
    return <p className="muted">{t('nothingToChart')}</p>;
  }

  const percentMode = viz.stacked === 'percent' && (kind === 'bar' || kind === 'hbar' || kind === 'area');
  const stacked = viz.stacked !== 'none' && (kind === 'bar' || kind === 'hbar' || kind === 'area');
  const margin = { top: 8, right: 16, bottom: 8, left: 0 };
  const grid = <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />;
  const tooltip = (
    <Tooltip
      contentStyle={TOOLTIP_CONTENT_STYLE}
      labelStyle={TOOLTIP_LABEL_STYLE}
      itemStyle={TOOLTIP_ITEM_STYLE}
      formatter={(value: unknown) => formatValue(value)}
      cursor={kind === 'scatter' ? { strokeDasharray: '3 3' } : undefined}
    />
  );
  const legend =
    data.series.length > 1 || kind === 'pie' ? (
      <Legend wrapperStyle={LEGEND_STYLE} formatter={legendText} />
    ) : null;
  const xAxisCategory = (
    <XAxis
      dataKey={X_KEY}
      tick={AXIS_TICK}
      tickFormatter={(v: unknown) => tickLabel(v)}
      interval="preserveStartEnd"
    />
  );
  const yAxisNumber = (
    <YAxis
      tick={AXIS_TICK}
      tickFormatter={(v: number) => (percentMode ? percent(v) : compactNumber(v))}
    />
  );

  const renderChart = () => {
    switch (kind) {
      case 'bar':
        return (
          <BarChart data={data.rows} margin={margin} stackOffset={percentMode ? 'expand' : undefined}>
            {grid}
            {xAxisCategory}
            {yAxisNumber}
            {tooltip}
            {legend}
            {data.series.map((s, i) => (
              <Bar
                key={s.key}
                dataKey={s.key}
                name={s.label}
                fill={seriesColor(i)}
                stackId={stacked ? 'a' : undefined}
                radius={stacked ? undefined : [4, 4, 0, 0]}
                maxBarSize={48}
              />
            ))}
          </BarChart>
        );
      case 'hbar':
        return (
          <BarChart
            data={data.rows}
            layout="vertical"
            margin={{ ...margin, left: 24 }}
            stackOffset={percentMode ? 'expand' : undefined}
          >
            {grid}
            <XAxis
              type="number"
              tick={AXIS_TICK}
              tickFormatter={(v: number) => (percentMode ? percent(v) : compactNumber(v))}
            />
            <YAxis
              type="category"
              dataKey={X_KEY}
              tick={AXIS_TICK}
              tickFormatter={(v: unknown) => tickLabel(v)}
              width={120}
            />
            {tooltip}
            {legend}
            {data.series.map((s, i) => (
              <Bar
                key={s.key}
                dataKey={s.key}
                name={s.label}
                fill={seriesColor(i)}
                stackId={stacked ? 'a' : undefined}
                radius={stacked ? undefined : [0, 4, 4, 0]}
                maxBarSize={32}
              />
            ))}
          </BarChart>
        );
      case 'line':
        return (
          <LineChart data={data.rows} margin={margin}>
            {grid}
            {xAxisCategory}
            {yAxisNumber}
            {tooltip}
            {legend}
            {data.series.map((s, i) => (
              <Line
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.label}
                stroke={seriesColor(i)}
                strokeWidth={2}
                dot={data.rows.length <= 30 ? { r: 3, strokeWidth: 0, fill: seriesColor(i) } : false}
                connectNulls
              />
            ))}
          </LineChart>
        );
      case 'area':
        return (
          <AreaChart data={data.rows} margin={margin} stackOffset={percentMode ? 'expand' : undefined}>
            {grid}
            {xAxisCategory}
            {yAxisNumber}
            {tooltip}
            {legend}
            {data.series.map((s, i) => (
              <Area
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.label}
                stroke={seriesColor(i)}
                fill={seriesColor(i)}
                fillOpacity={stacked ? 0.6 : 0.2}
                strokeWidth={2}
                stackId={stacked ? 'a' : undefined}
                connectNulls
              />
            ))}
          </AreaChart>
        );
      case 'radar':
        return (
          <RadarChart data={data.rows} margin={margin}>
            <PolarGrid stroke={GRID_STROKE} />
            <PolarAngleAxis dataKey={X_KEY} tick={AXIS_TICK} tickFormatter={(v: unknown) => tickLabel(v)} />
            <PolarRadiusAxis tick={AXIS_TICK} tickFormatter={(v: number) => compactNumber(v)} />
            {tooltip}
            {legend}
            {data.series.map((s, i) => (
              <Radar
                key={s.key}
                dataKey={s.key}
                name={s.label}
                stroke={seriesColor(i)}
                fill={seriesColor(i)}
                fillOpacity={0.25}
                strokeWidth={2}
              />
            ))}
          </RadarChart>
        );
      case 'combo':
        return (
          <ComposedChart data={data.rows} margin={margin}>
            {grid}
            {xAxisCategory}
            <YAxis
              yAxisId="left"
              tick={AXIS_TICK}
              tickFormatter={(v: number) => compactNumber(v)}
            />
            {viz.right_axis.length > 0 && (
              <YAxis
                yAxisId="right"
                orientation="right"
                tick={AXIS_TICK}
                tickFormatter={(v: number) => compactNumber(v)}
              />
            )}
            {tooltip}
            {legend}
            {data.series
              .map((s, i) => ({ ...s, color: seriesColor(i) }))
              .filter((s) => (viz.combo_types[s.label] ?? 'bar') === 'bar')
              .map((s) => (
                <Bar
                  key={s.key}
                  dataKey={s.key}
                  name={s.label}
                  fill={s.color}
                  yAxisId={viz.right_axis.includes(s.label) ? 'right' : 'left'}
                  radius={[4, 4, 0, 0]}
                  maxBarSize={48}
                />
              ))}
            {data.series
              .map((s, i) => ({ ...s, color: seriesColor(i) }))
              .filter((s) => viz.combo_types[s.label] === 'line')
              .map((s) => (
                <Line
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  name={s.label}
                  stroke={s.color}
                  strokeWidth={2}
                  dot={data.rows.length <= 30 ? { r: 3, strokeWidth: 0, fill: s.color } : false}
                  yAxisId={viz.right_axis.includes(s.label) ? 'right' : 'left'}
                  connectNulls
                />
              ))}
          </ComposedChart>
        );
      case 'pie':
        return (
          <PieChart margin={margin}>
            <Tooltip
              contentStyle={TOOLTIP_CONTENT_STYLE}
              labelStyle={TOOLTIP_LABEL_STYLE}
              itemStyle={TOOLTIP_ITEM_STYLE}
              formatter={(value: unknown) => {
                const n = typeof value === 'number' ? value : Number(value);
                const share = pieTotal > 0 ? ` (${percent(n / pieTotal)})` : '';
                return `${fullNumber(n)}${share}`;
              }}
            />
            <Legend wrapperStyle={LEGEND_STYLE} formatter={legendText} />
            <Pie
              data={pieData}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              outerRadius={120}
              innerRadius={60}
              paddingAngle={1}
            >
              {pieData.map((_entry, i) => (
                <Cell key={i} fill={seriesColor(i)} stroke="var(--surface)" strokeWidth={2} />
              ))}
            </Pie>
          </PieChart>
        );
      case 'scatter':
        return (
          <ScatterChart margin={{ ...margin, bottom: 16, left: 8 }}>
            {grid}
            <XAxis
              type="number"
              dataKey={X_KEY}
              name={viz.x_column ?? ''}
              tick={AXIS_TICK}
              tickFormatter={(v: number) => compactNumber(v)}
            />
            <YAxis
              type="number"
              dataKey={data.series[0]?.key}
              name={data.series[0]?.label}
              tick={AXIS_TICK}
              tickFormatter={(v: number) => compactNumber(v)}
            />
            <ZAxis range={[60, 60]} />
            {tooltip}
            <Scatter data={data.rows} name={data.series[0]?.label} fill={seriesColor(0)} />
          </ScatterChart>
        );
    }
  };

  const isEmpty = kind === 'pie' ? pieData.length === 0 : data.rows.length === 0;
  const radarTooFew = kind === 'radar' && !isEmpty && data.rows.length < 3;

  return (
    <div className="chart">
      {!hideControls && onVizChange && (
        <ChartControls result={result} viz={viz} onChange={onVizChange} />
      )}

      {isEmpty ? (
        <p className="muted">{kind === 'scatter' ? t('noNumericPlural') : t('noNumericSingle')}</p>
      ) : radarTooFew ? (
        <p className="muted">{t('radarNeedsRows')}</p>
      ) : (
        <>
          {data.truncatedSeries && (
            <p className="muted chart__hint">{t('tooManySeries', { count: MAX_SERIES })}</p>
          )}
          <div className="chart__canvas">
            <ResponsiveContainer width="100%" height={height}>
              {renderChart()}
            </ResponsiveContainer>
          </div>
        </>
      )}
    </div>
  );
}
