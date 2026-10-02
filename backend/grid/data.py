"""Reproducible source preparation. No future interpolation or inferred power units."""
from __future__ import annotations

import hashlib
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / 'data' / 'raw'
ARTIFACTS = ROOT / 'artifacts'
TZ = 'Asia/Kolkata'
WEATHER = ['temperature_c', 'humidity_pct', 'rain_mm', 'wind_kmh']
LOAD_FILE = RAW / 'india_hourly_demand.csv'
WEATHER_FILE = RAW / 'india_weather_central.csv'


def source_hashes() -> dict:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [LOAD_FILE, WEATHER_FILE]}


def prepare_data() -> tuple[pd.DataFrame, dict]:
    source = pd.read_csv(LOAD_FILE)
    if {'Year', 'Date', 'Hourly Demand Met (in MW)'}.issubset(source.columns):
        load = pd.DataFrame({'timestamp': pd.to_datetime(
            source['Year'].astype(str) + '-' + source['Date'].astype(str),
            format='%Y-%d-%b %I%p', errors='coerce'),
            'load_mw': pd.to_numeric(source['Hourly Demand Met (in MW)'], errors='coerce')})
        unit_assumption = 'Demand source is already labelled MW; values are used without conversion.'
        unit_conversion = 'No conversion applied.'
        geographic_scope = 'India-wide hourly demand; national coverage is taken from the supplied source.'
        provenance_note = 'Supplied India demand profile. Original source provenance and measurement definition should be documented separately.'
    else:
        load = pd.read_csv(LOAD_FILE, header=None, names=['timestamp', 'load_w'])
        load['timestamp'] = pd.to_datetime(load['timestamp'], format='mixed', errors='coerce')
        load['load_w'] = pd.to_numeric(load['load_w'], errors='coerce')
        load['load_mw'] = load['load_w'] / 1_000_000.0
        unit_assumption = 'Original values treated as watts at the project owner’s request; not verified by source documentation.'
        unit_conversion = 'MW = source load / 1,000,000'
        geographic_scope = 'Legacy regional demo series; exact coverage is unverified.'
        provenance_note = 'Legacy source report and CSV scope are not independently verified.'
    if load[['timestamp', 'load_mw']].isna().any().any() or (load['load_mw'] <= 0).any():
        raise ValueError('Invalid load timestamps or non-positive/missing load values. Review source first.')
    if load['timestamp'].duplicated().any():
        raise ValueError('Duplicate load timestamps; resolve before training.')
    load = load.sort_values('timestamp')
    load['timestamp'] = load['timestamp'].dt.tz_localize(TZ)
    expected = pd.date_range(load.timestamp.min(), load.timestamp.max(), freq='h')
    gaps = len(expected.difference(pd.DatetimeIndex(load.timestamp)))
    if gaps:
        raise ValueError(f'{gaps} missing load hours; refusing to shift across gaps.')

    metadata = pd.read_csv(WEATHER_FILE, nrows=1).iloc[0].to_dict()
    weather = pd.read_csv(WEATHER_FILE, skiprows=3)
    weather = weather.rename(columns={weather.columns[0]: 'weather_timestamp', weather.columns[1]: WEATHER[0],
                                      weather.columns[2]: WEATHER[1], weather.columns[3]: WEATHER[2],
                                      weather.columns[4]: WEATHER[3]})
    weather['weather_timestamp'] = pd.to_datetime(weather['weather_timestamp'], errors='raise').dt.tz_localize(str(metadata['timezone'])).dt.tz_convert(TZ)
    if weather.weather_timestamp.duplicated().any():
        raise ValueError('Duplicate weather timestamps.')
    weather = weather.sort_values('weather_timestamp')
    for col in WEATHER:
        weather[col] = pd.to_numeric(weather[col], errors='coerce')
    # UTC+8 becomes IST at xx:30. Use the latest known reading, never nearest/future.
    merged = pd.merge_asof(load, weather[['weather_timestamp'] + WEATHER], left_on='timestamp',
                           right_on='weather_timestamp', direction='backward', tolerance=pd.Timedelta('1h'))
    matched = merged[WEATHER].notna().all(axis=1)
    audit = {
        'load_rows': len(load), 'weather_rows': len(weather), 'matched_rows': int(matched.sum()),
        'unmatched_load_rows': int((~matched).sum()), 'duplicate_load_timestamps': 0, 'missing_load_hours': gaps,
        'load_start': load.timestamp.min().isoformat(), 'load_end': load.timestamp.max().isoformat(),
        'weather_start_ist': weather.weather_timestamp.min().isoformat(), 'weather_end_ist': weather.weather_timestamp.max().isoformat(),
        'overlap_start': merged.loc[matched, 'timestamp'].min().isoformat(),
        'overlap_end': merged.loc[matched, 'timestamp'].max().isoformat(),
        'load_min_mw': float(load.load_mw.min()), 'load_max_mw': float(load.load_mw.max()),
        'load_mean_mw': float(load.load_mw.mean()), 'weather_timezone': str(metadata['timezone']),
        'load_timezone': TZ, 'unit_assumption': unit_assumption,
        'unit_conversion': unit_conversion,
        'geographic_scope': geographic_scope,
        'weather_alignment': 'Convert Asia/Singapore to Asia/Kolkata; backward as-of join with 1-hour tolerance. Typical reading age: 30 minutes.',
        'weather_use': 'Historical weather observations, treated as available at their timestamp for this demo. No actual future weather is used.',
        'load_timezone_assumption': 'Unlabelled consumption timestamps assumed to be IST.',
        'source_url': '',
        'provenance_note': provenance_note,
        'source_hashes': source_hashes(),
    }
    return merged.set_index('timestamp'), audit


def feature_frame(data: pd.DataFrame, lead: int) -> pd.DataFrame:
    """One row per issue time. Every demand/weather lookup is <= that issue time."""
    if not 1 <= lead <= 24:
        raise ValueError('Lead must be 1–24 hours.')
    x = pd.DataFrame(index=data.index)
    demand = data.load_mw
    x['current_load'] = demand
    for lag in [1, 2, 3, 6, 12, 24, 48, 72, 168]:
        x[f'load_lag_{lag}h'] = demand.shift(lag)
    for window in [6, 24, 168]:
        roll = demand.rolling(window, min_periods=window)
        x[f'load_mean_{window}h'] = roll.mean()
        x[f'load_std_{window}h'] = roll.std()
    x['load_trend_3h'] = demand - demand.shift(3)
    x['load_trend_24h'] = demand - demand.shift(24)
    x['target_hour_yesterday'] = demand.shift(24 - lead)
    x['target_hour_last_week'] = demand.shift(168 - lead)
    target = data.index + pd.Timedelta(hours=lead)
    x['lead_hour'] = lead
    x['target_hour_sin'] = np.sin(2 * np.pi * target.hour / 24)
    x['target_hour_cos'] = np.cos(2 * np.pi * target.hour / 24)
    x['target_weekday'] = target.dayofweek
    x['target_weekend'] = (target.dayofweek >= 5).astype(int)
    x['target_month'] = target.month
    for col in WEATHER:
        x[f'weather_{col}'] = data[col]
        x[f'weather_{col}_lag24'] = data[col].shift(24)
        x[f'weather_{col}_target_yesterday'] = data[col].shift(24 - lead)
    x['weather_temperature_trend'] = data.temperature_c - data.temperature_c.shift(3)
    return x


def supervised(data: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    chunks = []
    for lead in range(1, 25):
        x = feature_frame(data, lead)
        columns = list(x.columns)
        x['target'] = data.load_mw.shift(-lead)
        x['origin'] = x.index
        x['target_time'] = x.index + pd.Timedelta(hours=lead)
        chunks.append(x)
    return pd.concat(chunks, ignore_index=True).dropna(subset=columns + ['target']), columns
