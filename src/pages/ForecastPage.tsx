import { useEffect, useState } from 'react';
import { Activity, ArrowDownRight, ArrowUpRight, CheckCircle2, ChevronLeft, ChevronRight, CloudRain, Download, Droplets, Eye, EyeOff, Gauge, Play, Thermometer, TrendingUp, TriangleAlert, Wind, Zap } from 'lucide-react';
import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api, apiUrl, date, formatGW, formatGWh, shortDate, time, useResource } from '../api';
import { axis, chartTheme, ErrorState, Intro, LinkArrow, Loading, MetricCard, Panel, PanelHeading, Status } from '../components';
import type { Evaluation, Forecast, HistoryRow, Horizon, Meta, ModelName } from '../types';

export default function ForecastPage({meta, navigate}: {meta: Meta; navigate: (id: string) => void}) {
  const [origin, setOrigin] = useState(meta.replay.default.slice(0, 16));
  const [draft, setDraft] = useState(origin);
  const [horizon, setHorizon] = useState<Horizon>(24);
  const [model, setModel] = useState<ModelName>('weather');
  const [band, setBand] = useState(true);
  const [baseline, setBaseline] = useState(false);
  const [temperature, setTemperature] = useState(false);
  const [actuals, setActuals] = useState<{key: string; rows: HistoryRow[]} | null>(null);
  const [revealBusy, setRevealBusy] = useState(false);
  const [revealError, setRevealError] = useState('');
  const params = new URLSearchParams({origin, horizon: String(horizon), model}).toString();
  const result = useResource<Forecast>(`forecast?${params}`);
  const evaluation = useResource<Evaluation>('evaluation');
  const f = result.data;
  const key = `${origin}/${horizon}/${model}`;
  const revealed = actuals?.key === key;
  useEffect(() => { setRevealError(''); }, [key]);
  async function reveal() {
    if (revealed) { setActuals(null); return; }
    setRevealBusy(true); setRevealError('');
    try { const response = await api<{actuals: HistoryRow[]}>(`actuals?${params}`); setActuals({key, rows: response.actuals}); }
    catch (e) { setRevealError(e instanceof Error ? e.message : 'Could not reveal actual demand.'); }
    finally { setRevealBusy(false); }
  }
  function moveDay(direction: number) {
    const next = new Date(`${origin}:00Z`); next.setUTCDate(next.getUTCDate() + direction);
    const value = next.toISOString().slice(0,16);
    if (value >= meta.replay.min.slice(0,16) && value <= meta.replay.max.slice(0,16)) { setOrigin(value); setDraft(value); }
  }
  const testMetric = evaluation.data?.models[model].by_window.find(x => x.hours === horizon);
  const actualByTime = new Map(revealed ? actuals.rows.map(r => [r.timestamp, r.load_mw]) : []);
  const replayMAE = f && revealed ? f.forecast.reduce((sum, r) => sum + Math.abs(r.predicted_mw - (actualByTime.get(r.timestamp) ?? r.predicted_mw)), 0) / horizon : null;
  const plot = f ? [
    ...f.history.map((r, i) => ({ timestamp: r.timestamp, observed: r.load_mw, prediction: i === f.history.length-1 ? r.load_mw : null, actual: i === f.history.length-1 && revealed ? r.load_mw : null })),
    ...f.forecast.map(r => ({ timestamp: r.timestamp, prediction: r.predicted_mw, interval: [r.lower_mw, r.upper_mw], baseline: r.baseline_mw, temperature: r.temperature_proxy_c, actual: actualByTime.get(r.timestamp) ?? null })),
  ] : [];
  const high = f?.forecast.filter(r => r.risk === 'High') ?? [];
  return <>
    <Intro eyebrow="FORECAST / HISTORICAL REPLAY" title="A clearer view of the next hour." text="Explore electricity demand, anticipate peaks, and put your model to the test." action={<a className="button" href={`${apiUrl(`forecast.csv?${params}`)}`}><Download size={15}/>Export forecast</a>}/>
    <Panel className="forecast-controls">
      <div className="control-group"><label>Forecast horizon</label><div className="segmented" aria-label="Forecast horizon">{([1,6,24] as Horizon[]).map(h => <button key={h} aria-pressed={horizon === h} className={horizon === h ? 'selected' : ''} onClick={() => setHorizon(h)}>Next {h} {h === 1 ? 'hour' : 'hours'}</button>)}</div></div>
      <form className="replay-form" onSubmit={e => { e.preventDefault(); setOrigin(draft); }}><div className="control-group"><label htmlFor="replay-time">Forecast issued at · IST</label><input id="replay-time" type="datetime-local" required step={3600} min={meta.replay.min.slice(0,16)} max={meta.replay.max.slice(0,16)} value={draft} onChange={e => setDraft(e.target.value)}/></div><button className="button primary" type="submit"><Play size={14} fill="currentColor"/>Run forecast</button></form>
      <div className="control-group model-control"><label htmlFor="forecast-model">Model</label><select id="forecast-model" value={model} onChange={e => setModel(e.target.value as ModelName)}><option value="weather">XGBoost + weather</option><option value="demand_only">XGBoost · demand only</option></select></div>
    </Panel>
    <div className="replay-context"><span><span className="status-dot"/>Replay window: {shortDate(meta.replay.min)} – {date(meta.replay.max)} · future actuals hidden until revealed</span><div><button aria-label="Previous replay day" disabled={origin.slice(0,10) <= meta.replay.min.slice(0,10)} onClick={() => moveDay(-1)}><ChevronLeft size={15}/></button><button aria-label="Next replay day" disabled={origin.slice(0,10) >= meta.replay.max.slice(0,10)} onClick={() => moveDay(1)}><ChevronRight size={15}/></button></div></div>
    {result.loading ? <Loading message="Generating XGBoost predictions…"/> : result.error ? <ErrorState message={result.error} retry={result.retry}/> : f && <>
      <div className="metric-grid">
        <MetricCard label="Observed demand" value={formatGW(f.summary.current_mw)} unit="GW" detail={`At ${time(f.origin)} IST · ${shortDate(f.origin)}`} icon={<Activity size={18}/>}/>
        <MetricCard label="Predicted peak" value={formatGW(f.summary.peak_mw)} unit="GW" detail={`${time(f.summary.peak_time)} IST · ${shortDate(f.summary.peak_time)}`} icon={<TrendingUp size={18}/>} tone="amber"/>
        <MetricCard label="Estimated energy" value={formatGWh(f.summary.estimated_energy_mwh)} unit="GWh" detail={`Over the next ${horizon} ${horizon === 1 ? 'hour' : 'hours'} · hourly-average assumption`} icon={<Zap size={18}/>} tone="violet"/>
        <MetricCard label={`Test MAE · next ${horizon}h`} value={testMetric ? formatGW(testMetric.mae_mw) : '—'} unit="GW" detail="Average absolute error across replay origins" icon={<Gauge size={18}/>} tone="teal"/>
      </div>
      <div className="forecast-layout">
        <Panel className="chart-panel"><PanelHeading title={`${horizon}-hour demand forecast`} detail={`Issued ${date(f.origin)}, ${time(f.origin)} IST · power in GW`} action={<span className="model-chip">XGBOOST</span>}/>
          <div className="chart-legend"><span><i className="legend-dot observed"/>Observed load</span><span><i className="legend-dot predicted"/>Forecast</span>{revealed && <span><i className="legend-dot actual"/>Revealed actual</span>}{band && <span><i className="legend-band"/>90% nominal interval</span>}</div>
          <div className="demand-chart" role="img" aria-label={`Forecast line chart showing ${horizon} future hourly predictions with historical context; exact values are in the table below.`}><ResponsiveContainer width="100%" height="100%"><ComposedChart data={plot} margin={{top:20, right:temperature ? 12 : 4, left:-20, bottom:5}}>
            <CartesianGrid vertical={false} stroke="#233146" strokeDasharray="3 4"/>
            <XAxis dataKey="timestamp" {...axis} tickFormatter={time} minTickGap={35}/>
          <YAxis yAxisId="load" {...axis} domain={['auto', 'auto']} tickFormatter={v => (Number(v)/1000).toFixed(0)} width={64}/>
            {temperature && <YAxis yAxisId="temp" orientation="right" {...axis} domain={['auto','auto']} tickFormatter={v => `${v}°`} width={38}/>}
          <Tooltip contentStyle={chartTheme} labelFormatter={v => `${shortDate(String(v))} · ${time(String(v))} IST`} formatter={(v, name) => [Array.isArray(v) ? v.map(n => (Number(n)/1000).toFixed(3)).join(' – ') + ' GW' : `${name === 'Yesterday’s temperature' ? Number(v).toFixed(1) : (Number(v)/1000).toFixed(3)} ${name === 'Yesterday’s temperature' ? '°C' : 'GW'}`, name]}/>
            {band && <Area yAxisId="load" type="monotone" dataKey="interval" name="Nominal interval" stroke="none" fill="#65b8ff" fillOpacity={.13} isAnimationActive={false}/>}
            <ReferenceLine yAxisId="load" x={f.origin} stroke="#8596b0" strokeDasharray="4 5" label={{value:'FORECAST START', position:'insideTopRight', fill:'#92a2b7', fontSize:9}}/>
            <Line yAxisId="load" dataKey="observed" name="Observed load" stroke="#68d9ba" strokeWidth={2.5} dot={false} isAnimationActive={false}/>
            <Line yAxisId="load" dataKey="prediction" name="XGBoost forecast" stroke="#70baff" strokeWidth={2.5} strokeDasharray="6 3" dot={horizon === 1 ? {r:4} : false} isAnimationActive={false}/>
            {revealed && <Line yAxisId="load" dataKey="actual" name="Revealed actual" stroke="#f1f5fc" strokeWidth={2} dot={horizon === 1 ? {r:3} : false} isAnimationActive={false}/>}
            {baseline && <Line yAxisId="load" dataKey="baseline" name="Same hour yesterday" stroke="#a896d9" strokeWidth={1.5} dot={false} isAnimationActive={false}/>}
            {temperature && <Line yAxisId="temp" dataKey="temperature" name="Yesterday’s temperature" stroke="#e6a65e" strokeWidth={1.5} dot={false} isAnimationActive={false}/>}
          </ComposedChart></ResponsiveContainer></div>
          <div className="chart-options"><label><input type="checkbox" checked={band} onChange={e => setBand(e.target.checked)}/>Uncertainty band</label><label><input type="checkbox" checked={baseline} onChange={e => setBaseline(e.target.checked)}/>Yesterday baseline</label><label><input type="checkbox" checked={temperature} onChange={e => setTemperature(e.target.checked)}/>Yesterday’s temperature</label></div>
          <div className="chart-caption">Intervals are calibrated estimates, not guarantees. {temperature && 'Temperature is yesterday’s corresponding reading, not a future weather forecast.'}<LinkArrow onClick={() => navigate('evaluation')}>Check measured coverage</LinkArrow></div>
        </Panel>
        <div className="forecast-side">
          <Panel className="weather-panel"><PanelHeading title="Weather at issue time" detail="Latest aligned central-India observation" action={<Thermometer size={19} className="text-amber"/>}/><div className="weather-temperature">{f.weather.temperature_c.toFixed(1)}<span>°C</span></div><p className="weather-location">Central India reference · {time(f.weather.timestamp)} IST</p><div className="weather-list"><span><Droplets size={15}/>Humidity<b>{f.weather.humidity_pct.toFixed(0)}%</b></span><span><CloudRain size={15}/>Rainfall<b>{f.weather.rain_mm.toFixed(1)} mm</b></span><span><Wind size={15}/>Wind<b>{f.weather.wind_kmh.toFixed(1)} km/h</b></span></div><div className="weather-note">{model === 'weather' ? 'This model uses recent weather and past demand.' : 'This model uses demand and calendar features only.'}</div></Panel>
          <Panel className="reveal-panel"><span className="eyebrow">PUT THE FORECAST TO THE TEST</span><h3>{revealed ? 'Reality, revealed.' : 'How close did we get?'}</h3><p>{revealed ? `This replay’s MAE is ${formatGW(replayMAE!)} GW. Compare every prediction in the table.` : 'Overlay the held-out observations and compare them with your predictions.'}</p><button className={`button ${revealed ? '' : 'primary'}`} onClick={reveal} disabled={revealBusy}>{revealed ? <EyeOff size={15}/> : <Eye size={15}/>} {revealBusy ? 'Revealing…' : revealed ? 'Hide actual demand' : 'Reveal actual demand'}</button>{revealError && <p role="alert" className="error-text">{revealError}</p>}</Panel>
        </div>
      </div>
      <div className={`peak-notice ${high.length ? 'warning' : ''}`}><div className="notice-icon">{high.length ? <TriangleAlert size={20}/> : <CheckCircle2 size={20}/>}</div><div><b>{high.length ? 'Elevated peak demand ahead' : 'Forecast stays below the demo peak threshold'}</b><p>{high.length ? `${high.length} forecast hour${high.length > 1 ? 's' : ''} exceed ${formatGW(f.threshold_mw)} GW. Peak: ${formatGW(f.summary.peak_mw)} GW at ${time(f.summary.peak_time)} IST.` : `Expected peak ${formatGW(f.summary.peak_mw)} GW · threshold ${formatGW(f.threshold_mw)} GW.`} Threshold is historical, not grid capacity.</p></div><span className="peak-change">{f.summary.peak_change_pct >= 0 ? <ArrowUpRight size={19}/> : <ArrowDownRight size={19}/>} {f.summary.peak_change_pct >= 0 ? '+' : ''}{f.summary.peak_change_pct.toFixed(1)}%<small>peak vs current</small></span></div>
      <Panel className="table-panel"><PanelHeading title="Hour-by-hour outlook" detail="Forecast, calibrated range, and demand change from the previous hour" action={<span className="subtle-badge">{horizon} prediction{horizon > 1 ? 's' : ''}</span>}/><div className="table-scroll"><table><thead><tr><th>Time · IST</th><th>Forecast · GW</th><th>90% range · GW</th>{revealed && <th>Actual · GW</th>}<th>Change</th><th>Load status</th></tr></thead><tbody>{f.forecast.map(r => <tr key={r.timestamp}><td><b>{time(r.timestamp)}</b><span className="cell-note">{shortDate(r.timestamp)}</span></td><td className="number emphasis">{formatGW(r.predicted_mw)}</td><td className="number muted">{formatGW(r.lower_mw)} – {formatGW(r.upper_mw)}</td>{revealed && <td className="number">{formatGW(actualByTime.get(r.timestamp)!)}</td>}<td className="number">{r.change_pct > 0 ? '+' : ''}{r.change_pct.toFixed(1)}%</td><td><Status value={r.risk}/></td></tr>)}</tbody></table></div><p className="table-footnote">Demand is supplied in MW and displayed here in GW. Regional weather is a central-India reference for India-wide demand.</p></Panel>
    </>}
  </>;
}
