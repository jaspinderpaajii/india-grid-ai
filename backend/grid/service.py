from __future__ import annotations
import json
import math
from functools import lru_cache
import numpy as np
import pandas as pd
from xgboost import XGBRegressor
from .data import ARTIFACTS, TZ, feature_frame, prepare_data, source_hashes


def records(frame: pd.DataFrame) -> list[dict]:
    result = []
    for timestamp, row in frame.iterrows():
        entry = {'timestamp': timestamp.isoformat()}
        for key, value in row.items():
            if pd.isna(value):
                entry[key] = None
            elif isinstance(value, pd.Timestamp):
                entry[key] = value.isoformat()
            elif isinstance(value, (float, int, np.number)):
                entry[key] = float(value)
            else:
                entry[key] = value
        result.append(entry)
    return result


class GridService:
    def __init__(self):
        path = ARTIFACTS / 'report.json'
        if not path.exists():
            raise RuntimeError('Models are not trained. Run: python -m backend.train')
        self.report = json.loads(path.read_text(encoding='utf-8'))
        if source_hashes() != self.report['audit']['source_hashes']:
            raise RuntimeError('Source data changed. Retrain before serving forecasts.')
        self.data, self.audit = prepare_data()
        self.models = {}
        self.frames = {h: feature_frame(self.data, h) for h in range(1, 25)}
        for name, filename in self.report['model_files'].items():
            model = XGBRegressor()
            model.load_model(ARTIFACTS / filename)
            self.models[name] = model

    def origin(self, value: str | None) -> pd.Timestamp:
        try:
            ts = pd.Timestamp(value or self.report['replay']['default'])
            ts = ts.tz_localize(TZ) if ts.tzinfo is None else ts.tz_convert(TZ)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError('Use a valid hourly timestamp in IST.') from exc
        if pd.isna(ts) or ts not in self.data.index:
            raise ValueError('Select an exact hourly timestamp from the dataset.')
        if not pd.Timestamp(self.report['replay']['min']) <= ts <= pd.Timestamp(self.report['replay']['max']):
            raise ValueError('Replay is restricted to the held-out test period.')
        return ts

    def forecast(self, origin: str | None, horizon: int, model_name: str) -> dict:
        ts = self.origin(origin)
        columns = self.report['columns'][model_name]
        x = pd.concat([self.frames[h].loc[[ts]] for h in range(1, horizon + 1)])
        baseline = x.target_hour_yesterday.to_numpy()
        decay = self.report['parameters'][model_name]['decay_hours']
        anchor = baseline + x.load_trend_24h.to_numpy() * np.exp(-x.lead_hour.to_numpy() / decay)
        predicted = np.maximum(0, anchor + self.models[model_name].predict(x[columns]))
        threshold = self.report['peak_threshold_mw']
        rows = []
        current = float(self.data.loc[ts, 'load_mw'])
        for i, value in enumerate(predicted):
            lead = i + 1
            radius = self.report['intervals'][model_name][str(lead)]
            previous = current if i == 0 else predicted[i - 1]
            rows.append({'timestamp': (ts + pd.Timedelta(hours=lead)).isoformat(), 'lead': lead,
                         'predicted_mw': float(value), 'lower_mw': max(0, float(value) - radius),
                         'upper_mw': float(value) + radius, 'baseline_mw': float(baseline[i]),
                         'temperature_proxy_c': float(x.iloc[i].weather_temperature_c_target_yesterday),
                         'change_pct': float((value / previous - 1) * 100),
                         'risk': 'High' if value >= threshold else 'Elevated' if value >= threshold * .9 else 'Normal'})
        peak = max(rows, key=lambda r: r['predicted_mw'])
        observed = self.data.loc[ts]
        return {'origin': ts.isoformat(), 'horizon': horizon, 'model': model_name, 'unit': 'MW',
                'summary': {'current_mw': current, 'peak_mw': peak['predicted_mw'], 'peak_time': peak['timestamp'],
                            'average_mw': float(predicted.mean()), 'minimum_mw': float(predicted.min()),
                            'estimated_energy_mwh': float(predicted.sum()), 'peak_change_pct': float((peak['predicted_mw']/current - 1) * 100)},
                'weather': {'temperature_c': float(observed.temperature_c), 'humidity_pct': float(observed.humidity_pct),
                            'rain_mm': float(observed.rain_mm), 'wind_kmh': float(observed.wind_kmh),
                            'timestamp': observed.weather_timestamp.isoformat()},
                'history': records(self.data.loc[ts-pd.Timedelta('23h'):ts, ['load_mw']]),
                'forecast': rows, 'threshold_mw': threshold,
                'energy_note': 'Estimated by summing hourly forecast MW × 1 hour; treats each forecast as the interval-average demand.'}

    def actuals(self, origin, horizon):
        ts = self.origin(origin)
        return records(self.data.loc[ts+pd.Timedelta('1h'):ts+pd.Timedelta(hours=horizon), ['load_mw']])

    def history(self, start: str | None, end: str | None, query: str = '') -> pd.DataFrame:
        frame = self.data
        if start:
            lower = pd.Timestamp(start).tz_localize(TZ)
            frame = frame.loc[frame.index >= lower]
        if end:
            upper = pd.Timestamp(end).tz_localize(TZ) + pd.Timedelta('1d')
            frame = frame.loc[frame.index < upper]
        if start and end and start > end:
            raise ValueError('Start date must not be after end date.')
        if query:
            labels = pd.Index(frame.index.strftime('%Y-%m-%d %H:%M'))
            frame = frame[labels.str.contains(query.strip(), regex=False)]
        return frame

    def analytics(self) -> dict:
        data = self.data.copy()
        daily = data.resample('D').agg(average_mw=('load_mw', 'mean'), peak_mw=('load_mw', 'max'))
        hours = data.groupby(data.index.hour).load_mw.mean()
        weekdays = data.groupby(data.index.dayofweek).load_mw.mean()
        heat = data.groupby([data.index.dayofweek, data.index.hour // 4]).load_mw.mean()
        corr = data[['load_mw', 'temperature_c']].dropna().corr().iloc[0, 1]
        scatter = data.dropna(subset=['temperature_c']).iloc[::24]
        climate = data.dropna(subset=['temperature_c', 'humidity_pct']).copy()
        climate['temperature_band'] = pd.cut(
            climate.temperature_c,
            bins=[-np.inf, 15, 20, 25, 30, 35, np.inf],
            labels=['<15°C', '15–20°C', '20–25°C', '25–30°C', '30–35°C', '35°C+']
        )
        bands = climate.groupby('temperature_band', observed=False).agg(
            average_mw=('load_mw', 'mean'), peak_mw=('load_mw', 'max'),
            average_temperature_c=('temperature_c', 'mean'), records=('load_mw', 'size')
        ).reset_index()
        daily_climate = climate.resample('D').agg(
            average_temperature_c=('temperature_c', 'mean'),
            average_mw=('load_mw', 'mean'), peak_mw=('load_mw', 'max')
        ).dropna()
        hot_threshold = float(daily_climate.average_temperature_c.quantile(.90))
        hot = daily_climate.average_temperature_c >= hot_threshold
        hot_avg = float(daily_climate.loc[hot, 'average_mw'].mean())
        other_avg = float(daily_climate.loc[~hot, 'average_mw'].mean())

        # Estimate the temperature association after controlling for time-of-day,
        # weekday, month, and recent demand. This is still observational, not causal.
        regression = climate.copy()
        regression['lag_1h'] = regression.load_mw.shift(1)
        regression['lag_24h'] = regression.load_mw.shift(24)
        regression = regression.dropna()
        hour_dummies = pd.get_dummies(regression.index.hour, drop_first=True, dtype=float)
        weekday_dummies = pd.get_dummies(regression.index.dayofweek, drop_first=True, dtype=float)
        month_dummies = pd.get_dummies(regression.index.month, drop_first=True, dtype=float)
        x = np.column_stack([
            np.ones(len(regression)), regression.temperature_c.to_numpy(),
            np.square(regression.temperature_c.to_numpy()),
            regression.lag_1h.to_numpy(), regression.lag_24h.to_numpy(),
            hour_dummies.to_numpy(), weekday_dummies.to_numpy(), month_dummies.to_numpy()
        ])
        y = regression.load_mw.to_numpy()
        beta = np.linalg.lstsq(x, y, rcond=None)[0]
        residual = y - x @ beta
        controlled_r2 = 1 - (residual @ residual) / ((y - y.mean()) @ (y - y.mean()))
        return {'daily': records(daily),
                'hourly': [{'hour': int(h), 'load_mw': float(v)} for h, v in hours.items()],
                'weekdays': [{'day': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][int(d)], 'load_mw': float(v)} for d, v in weekdays.items()],
                'heatmap': [{'day': int(d), 'block': int(b), 'load_mw': float(v)} for (d, b), v in heat.items()],
                'scatter': [{'temperature_c': float(r.temperature_c), 'load_mw': float(r.load_mw)} for _, r in scatter.iterrows()],
                'temperature_correlation': float(corr),
                'climate': {
                    'temperature_bands': [
                        {'band': str(r.temperature_band), 'average_mw': float(r.average_mw),
                         'peak_mw': float(r.peak_mw), 'average_temperature_c': float(r.average_temperature_c),
                         'records': int(r.records)} for _, r in bands.iterrows() if pd.notna(r.average_mw)
                    ],
                    'daily': records(daily_climate.iloc[::2]),
                    'hot_days': {
                        'threshold_c': hot_threshold, 'count': int(hot.sum()),
                        'hot_average_mw': hot_avg, 'other_average_mw': other_avg,
                        'difference_pct': float((hot_avg / other_avg - 1) * 100)
                    },
                    'controlled_temperature_mw_per_c': float(beta[1] + 2 * beta[2] * 30),
                    'controlled_r2': float(controlled_r2),
                    'controlled_note': 'Marginal temperature association at 30°C from an observational quadratic regression controlling for hour, weekday, month, 1-hour lag demand, and 24-hour lag demand.'
                }}


@lru_cache(maxsize=1)
def get_service() -> GridService:
    return GridService()
