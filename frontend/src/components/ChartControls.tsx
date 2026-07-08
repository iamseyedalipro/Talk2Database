import { useTranslation } from 'react-i18next';
import type { ComboSeriesType, ExecuteResponse, WidgetViz } from '../api/types';
import { MAX_SERIES, numericColumns } from '../utils/chartData';
import { normalizeViz } from '../utils/viz';

interface Props {
  result: ExecuteResponse;
  viz: WidgetViz;
  onChange: (viz: WidgetViz) => void;
}

/**
 * The chart configuration controls: X axis, Y column(s), series grouping,
 * stacking, pie mode, and combo mark/axis assignment. Shared by the ad-hoc
 * results view and the dashboard widget editor so both stay identical.
 */
export default function ChartControls({ result, viz, onChange }: Props) {
  const { t } = useTranslation('results');
  const kind = viz.view;
  const numericCols = numericColumns(result);
  const yOptions = numericCols.length > 0 ? numericCols : result.columns.map((c) => c.name);
  const xOptions =
    kind === 'scatter' && numericCols.length > 0
      ? result.columns.filter((c) => numericCols.includes(c.name))
      : result.columns;

  const update = (patch: Partial<WidgetViz>) => onChange(normalizeViz({ ...viz, ...patch }));

  // Contexts where the long shape / multiple Y columns do not apply.
  const singleY =
    kind === 'scatter' || viz.series_column !== null || (kind === 'pie' && viz.pie_mode === 'category');
  const supportsSeries =
    kind === 'bar' || kind === 'hbar' || kind === 'line' || kind === 'area' || kind === 'radar';
  const supportsStack = kind === 'bar' || kind === 'hbar' || kind === 'area';

  const toggleY = (name: string) => {
    const selected = viz.y_columns.includes(name);
    if (selected) {
      const next = viz.y_columns.filter((c) => c !== name);
      update({ y_columns: next });
    } else if (viz.y_columns.length < MAX_SERIES) {
      update({ y_columns: [...viz.y_columns, name] });
    }
  };

  const setComboType = (name: string, type: ComboSeriesType) => {
    update({ combo_types: { ...viz.combo_types, [name]: type } });
  };
  const setComboAxis = (name: string, right: boolean) => {
    const next = viz.right_axis.filter((c) => c !== name);
    update({ right_axis: right ? [...next, name] : next });
  };

  return (
    <div className="chart__controls">
      <label className="field field--inline">
        <span>{kind === 'scatter' ? t('xAxisNumeric') : t('xAxis')}</span>
        <select
          value={viz.x_column ?? ''}
          onChange={(e) => update({ x_column: e.target.value || null })}
        >
          <option value="">{t('auto')}</option>
          {xOptions.map((col) => (
            <option key={col.name} value={col.name}>
              {col.name}
            </option>
          ))}
        </select>
      </label>

      {kind === 'pie' && (
        <label className="field field--inline">
          <span>{t('pieMode')}</span>
          <select
            value={viz.pie_mode}
            onChange={(e) => update({ pie_mode: e.target.value as WidgetViz['pie_mode'] })}
          >
            <option value="category">{t('pieByCategory')}</option>
            <option value="columns">{t('pieByColumns')}</option>
          </select>
        </label>
      )}

      {singleY ? (
        <label className="field field--inline">
          <span>{t('yAxisNumeric')}</span>
          <select
            value={viz.y_columns[0] ?? ''}
            onChange={(e) => update({ y_columns: e.target.value ? [e.target.value] : [] })}
          >
            <option value="">{t('auto')}</option>
            {yOptions.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <div className="field field--inline chart__chips-field">
          <span>{t('yColumns')}</span>
          <div className="chart__chips" role="group" aria-label={t('yColumns')}>
            {yOptions.map((name) => {
              const active = viz.y_columns.includes(name);
              const disabled = !active && viz.y_columns.length >= MAX_SERIES;
              return (
                <button
                  key={name}
                  type="button"
                  className={`chart__chip${active ? ' is-active' : ''}`}
                  aria-pressed={active}
                  disabled={disabled}
                  onClick={() => toggleY(name)}
                >
                  {name}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {supportsSeries && (
        <label className="field field--inline">
          <span>{t('seriesColumn')}</span>
          <select
            value={viz.series_column ?? ''}
            onChange={(e) => update({ series_column: e.target.value || null })}
          >
            <option value="">{t('none')}</option>
            {result.columns.map((col) => (
              <option key={col.name} value={col.name}>
                {col.name}
              </option>
            ))}
          </select>
        </label>
      )}

      {supportsStack && (
        <label className="field field--inline">
          <span>{t('stacking')}</span>
          <select
            value={viz.stacked}
            onChange={(e) => update({ stacked: e.target.value as WidgetViz['stacked'] })}
          >
            <option value="none">{t('stackNone')}</option>
            <option value="stacked">{t('stackStacked')}</option>
            <option value="percent">{t('stackPercent')}</option>
          </select>
        </label>
      )}

      {kind === 'combo' && viz.y_columns.length > 0 && (
        <div className="chart__combo">
          {viz.y_columns.map((name) => {
            const mark = viz.combo_types[name] ?? 'bar';
            const right = viz.right_axis.includes(name);
            return (
              <div key={name} className="chart__combo-row">
                <span className="chart__combo-name" title={name}>
                  {name}
                </span>
                <div className="chart-toggle" role="group" aria-label={name}>
                  <button
                    type="button"
                    className={`chart-toggle__btn${mark === 'bar' ? ' is-active' : ''}`}
                    onClick={() => setComboType(name, 'bar')}
                  >
                    {t('markBar')}
                  </button>
                  <button
                    type="button"
                    className={`chart-toggle__btn${mark === 'line' ? ' is-active' : ''}`}
                    onClick={() => setComboType(name, 'line')}
                  >
                    {t('markLine')}
                  </button>
                </div>
                <div className="chart-toggle" role="group" aria-label={`${name} axis`}>
                  <button
                    type="button"
                    className={`chart-toggle__btn${right ? '' : ' is-active'}`}
                    onClick={() => setComboAxis(name, false)}
                  >
                    {t('axisLeft')}
                  </button>
                  <button
                    type="button"
                    className={`chart-toggle__btn${right ? ' is-active' : ''}`}
                    onClick={() => setComboAxis(name, true)}
                  >
                    {t('axisRight')}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
