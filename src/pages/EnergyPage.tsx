import { useState } from 'react';
import { AlertTriangle, BatteryCharging, CalendarClock, Gauge, Zap } from 'lucide-react';
import { Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { formatGW, formatGWh, shortDate, time, useResource } from '../api';
import { axis, chartTheme, ErrorState, Intro, Loading, MetricCard, Panel, PanelHeading } from '../components';
import type { Forecast, Horizon, Meta, ModelName } from '../types';

export default function EnergyPage({meta}: {meta: Meta}) {
  const [draft, setDraft] = useState(meta.replay.default.slice(0,16));
  const [origin, setOrigin] = useState(meta.replay.default);
  const [horizon, setHorizon] = useState<Horizon>(24);
  const [model, setModel] = useState<ModelName>('weather');
  const params = new URLSearchParams({origin, horizon: String(horizon), model}).toString();
  const result = useResource<Forecast>(`forecast?${params}`);
  const f = result.data;
  const series = f?.forecast.map((row, index) => ({
    timestamp: row.timestamp,
    demand_gw: row.predicted_mw / 1000,
    lower_gw: row.lower_mw / 1000,
    upper_gw: row.upper_mw / 1000,
    cumulative_gwh: f.forecast.slice(0,index + 1).reduce((sum, item) => sum + item.predicted_mw, 0) / 1000,
  })) ?? [];
  const highHours = f?.forecast.filter(row => row.risk === 'High').length ?? 0;
  return <>
    <Intro eyebrow="ENERGY PLANNING / DEMAND NEED" title="How much energy will the grid need?" text="Convert the hourly demand forecast into a planning view of expected power, energy, peaks, and uncertainty."/>
    <Panel className="forecast-controls"><form className="replay-form" onSubmit={e=>{e.preventDefault();setOrigin(draft);}}><div className="control-group"><label htmlFor="energy-origin">Forecast issued at · IST</label><input id="energy-origin" type="datetime-local" required step={3600} min={meta.replay.min.slice(0,16)} max={meta.replay.max.slice(0,16)} value={draft} onChange={e=>setDraft(e.target.value)}/></div><button className="button primary" type="submit"><CalendarClock size={14}/>Update plan</button></form><div className="control-group model-control"><label htmlFor="energy-horizon">Planning horizon</label><select id="energy-horizon" value={horizon} onChange={e=>setHorizon(Number(e.target.value) as Horizon)}><option value={1}>Next 1 hour</option><option value={6}>Next 6 hours</option><option value={24}>Next 24 hours</option></select></div><div className="control-group model-control"><label htmlFor="energy-model">Forecast model</label><select id="energy-model" value={model} onChange={e=>setModel(e.target.value as ModelName)}><option value="weather">Weather-aware</option><option value="demand_only">Demand only</option></select></div></Panel>
    {result.loading?<Loading message="Calculating energy demand plan…"/>:result.error?<ErrorState message={result.error} retry={result.retry}/>:f&&<>
      <div className="metric-grid"><MetricCard label="Estimated energy" value={formatGWh(f.summary.estimated_energy_mwh)} unit="GWh" detail={`Across the next ${horizon} forecast hour${horizon>1?'s':''}`} icon={<BatteryCharging size={18}/>} tone="violet"/><MetricCard label="Average demand" value={formatGW(f.summary.average_mw)} unit="GW" detail="Mean hourly demand across the horizon" icon={<Gauge size={18}/>}/><MetricCard label="Expected peak" value={formatGW(f.summary.peak_mw)} unit="GW" detail={`Expected at ${time(f.summary.peak_time)} IST · ${shortDate(f.summary.peak_time)}`} icon={<Zap size={18}/>} tone="amber"/><MetricCard label="High-demand hours" value={String(highHours)} detail="Hours above the historical planning threshold" icon={<AlertTriangle size={18}/>} tone="teal"/></div>
      <Panel className="chart-panel"><PanelHeading title="Demand and cumulative energy" detail="Power demand in GW · cumulative energy in GWh" action={<span className="model-chip">{model === 'weather' ? 'WEATHER-AWARE' : 'DEMAND ONLY'}</span>}/><div className="medium-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={series} margin={{left:8,right:12,top:12,bottom:5}}><CartesianGrid stroke="#233146" vertical={false}/><XAxis dataKey="timestamp" {...axis} tickFormatter={v=>time(String(v))}/><YAxis yAxisId="demand" width={58} {...axis} tickFormatter={v=>`${Number(v).toFixed(0)} GW`}/><YAxis yAxisId="energy" orientation="right" width={62} {...axis} tickFormatter={v=>`${Number(v).toFixed(0)} GWh`}/><Tooltip contentStyle={chartTheme} labelFormatter={v=>`${shortDate(String(v))} · ${time(String(v))} IST`} formatter={(v,name)=>[`${Number(v).toFixed(3)} ${name === 'Cumulative energy' ? 'GWh' : 'GW'}`,name]}/><Area yAxisId="demand" dataKey="upper_gw" name="Upper range" stroke="none" fill="#70baff" fillOpacity={.08}/><Area yAxisId="demand" dataKey="lower_gw" name="Lower range" stroke="none" fill="#0d1726" fillOpacity={1}/><Line yAxisId="demand" dataKey="demand_gw" name="Expected demand" stroke="#70baff" strokeWidth={2.5} dot={{r:2}}/><Line yAxisId="energy" dataKey="cumulative_gwh" name="Cumulative energy" stroke="#68d9ba" strokeWidth={2} dot={false}/></LineChart></ResponsiveContainer></div></Panel>
      <div className="data-notice"><BatteryCharging size={17}/><p><b>Planning interpretation.</b> Estimated energy is the sum of hourly demand in GW × 1 hour. It is a planning estimate, not a guaranteed generation requirement or grid-capacity limit.</p></div>
    </>}
  </>;
}
