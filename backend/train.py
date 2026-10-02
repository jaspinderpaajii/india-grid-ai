"""Run: python -m backend.train. Chronological tuning, calibration, final test."""
from __future__ import annotations

import json
import math
import platform
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import sklearn
import xgboost
from xgboost import XGBRegressor
from backend.grid.data import ARTIFACTS, ROOT, TZ, prepare_data, supervised

TRAIN_END = pd.Timestamp('2023-09-30 23:00', tz=TZ)
VALID_START = pd.Timestamp('2023-10-01', tz=TZ)
VALID_END = pd.Timestamp('2023-11-30 23:00', tz=TZ)
CAL_START = pd.Timestamp('2023-12-01', tz=TZ)
CAL_END = pd.Timestamp('2023-12-31 23:00', tz=TZ)
TEST_START = pd.Timestamp('2024-01-01', tz=TZ)


def metrics(actual, predicted) -> dict:
    error = np.asarray(predicted) - np.asarray(actual)
    return {'mae_mw': float(np.abs(error).mean()), 'rmse_mw': float(np.sqrt(np.mean(error**2))),
            'wape_pct': float(np.abs(error).sum() / np.abs(actual).sum() * 100), 'n': len(error)}


def anchor(rows, decay_hours):
    # Extrapolate the most recent day-over-day level change, decaying with lead time.
    # This gives short forecasts recent context without requiring tree extrapolation.
    return rows.target_hour_yesterday.to_numpy() + rows.load_trend_24h.to_numpy() * np.exp(-rows.lead_hour.to_numpy() / decay_hours)


def predict(model, rows, columns, decay_hours):
    return np.maximum(0, anchor(rows, decay_hours) + model.predict(rows[columns]))


def main():
    ARTIFACTS.mkdir(exist_ok=True)
    data, audit = prepare_data()
    print('Data audit:', json.dumps(audit, indent=2, ensure_ascii=True), flush=True)
    rows, all_columns = supervised(data)
    train = rows[rows.target_time <= TRAIN_END]
    valid = rows[(rows.origin >= VALID_START) & (rows.target_time <= VALID_END)]
    fit = rows[rows.target_time <= VALID_END]
    calibration = rows[(rows.origin >= CAL_START) & (rows.target_time <= CAL_END)]
    last_origin = data.index.max() - pd.Timedelta('24h')
    test = rows[(rows.origin >= TEST_START) & (rows.origin <= last_origin)]
    assert train.target_time.max() < valid.origin.min()
    assert fit.target_time.max() < calibration.origin.min()
    assert calibration.target_time.max() < test.origin.min()
    splits = {name: {'origin_start': part.origin.min().isoformat(), 'origin_end': part.origin.max().isoformat(),
                     'target_end': part.target_time.max().isoformat(), 'samples': len(part), 'origins': int(part.origin.nunique())}
              for name, part in [('train', train), ('validation', valid), ('calibration', calibration), ('test', test)]}
    settings = [dict(max_depth=depth, min_child_weight=30, decay_hours=decay) for depth in [3, 5] for decay in [3, 12, 24]]
    report = {'audit': audit, 'splits': splits, 'models': {}, 'intervals': {}, 'feature_importance': [],
              'trained_at': datetime.now(timezone.utc).isoformat(), 'versions': {'python': platform.python_version(), 'xgboost': xgboost.__version__, 'pandas': pd.__version__, 'sklearn': sklearn.__version__},
              'method': 'Pooled direct multi-horizon XGBoost. Yesterday’s target-hour load is adjusted by a decaying latest day-over-day change, then XGBoost predicts the residual. Parameters are selected on the 2023 autumn validation period. 24 leads; no recursive predictions.',
              'evaluation_note': 'Parameters and boosting rounds are selected on October–November 2023. December 2023 calibrates intervals. January–April 2024 is held out. Overlapping hourly forecast windows are not independent observations.',
              'interval_note': '90% nominal, horizon-specific absolute residual calibration. Time-series dependence and seasonal changes mean 90% future coverage is not guaranteed. Measured test coverage is reported.',
              'weather_note': 'Only current and past weather used, including yesterday’s target-hour weather as a causal proxy. These are not archived weather forecasts.',
              'model_files': {}, 'columns': {}, 'parameters': {}, 'validation_trials': [],
              'development_note': 'Fixed chronological holdout used for project development evaluation, not an independent external benchmark. A first daily-anchor prototype was evaluated before this recent-level-adjusted version; final parameter selection uses the 2023 autumn validation period.'}
    predictions = test[['origin', 'target_time', 'lead_hour', 'target', 'target_hour_yesterday', 'target_hour_last_week', 'current_load']].copy()
    predictions = predictions.rename(columns={'target': 'actual', 'target_hour_yesterday': 'daily', 'target_hour_last_week': 'weekly', 'current_load': 'persistence'})
    for name, columns in [('demand_only', [c for c in all_columns if not c.startswith('weather_')]), ('weather', all_columns)]:
        best = None
        for params in settings:
            tree_params = {k: v for k, v in params.items() if k != 'decay_hours'}
            model = XGBRegressor(n_estimators=650, learning_rate=.035, objective='reg:squarederror', eval_metric='mae',
                                 tree_method='hist', n_jobs=4, random_state=42, subsample=.85, colsample_bytree=.9,
                                 reg_lambda=5, early_stopping_rounds=45, **tree_params)
            model.fit(train[columns], train.target.to_numpy() - anchor(train, params['decay_hours']),
                      eval_set=[(valid[columns], valid.target.to_numpy() - anchor(valid, params['decay_hours']))], verbose=False)
            score = metrics(valid.target.to_numpy(), predict(model, valid, columns, params['decay_hours']))
            trial = {'model': name, **params, 'trees': model.best_iteration + 1, **score}
            report['validation_trials'].append(trial)
            print('Validation:', json.dumps(trial), flush=True)
            if best is None or score['mae_mw'] < best['mae_mw']:
                best = trial
        final = XGBRegressor(n_estimators=best['trees'], max_depth=best['max_depth'], min_child_weight=best['min_child_weight'],
                             learning_rate=.035, objective='reg:squarederror', tree_method='hist', n_jobs=4,
                             random_state=42, subsample=.85, colsample_bytree=.9, reg_lambda=5)
        final.fit(fit[columns], fit.target.to_numpy() - anchor(fit, best['decay_hours']))
        final.save_model(ARTIFACTS / f'{name}.json')
        report['model_files'][name] = f'{name}.json'
        report['columns'][name] = columns
        report['parameters'][name] = best
        predictions[name] = predict(final, test, columns, best['decay_hours'])
        residual = calibration[['lead_hour']].copy()
        residual['error'] = np.abs(predict(final, calibration, columns, best['decay_hours']) - calibration.target.to_numpy())
        radii = {}
        for lead, group in residual.groupby('lead_hour'):
            q = min(1, math.ceil((len(group) + 1) * .90) / len(group))
            radii[str(int(lead))] = float(np.quantile(group.error, q, method='higher'))
        report['intervals'][name] = radii
        if name == 'weather':
            importance = sorted(zip(columns, final.feature_importances_.tolist()), key=lambda x: x[1], reverse=True)
            report['feature_importance'] = [{'feature': f, 'gain': float(g)} for f, g in importance]
        print(f'Final {name}:', metrics(test.target.to_numpy(), predictions[name].to_numpy()), flush=True)
    for name in ['daily', 'weekly', 'persistence', 'demand_only', 'weather']:
        result = {'overall': metrics(predictions.actual.to_numpy(), predictions[name].to_numpy()), 'by_lead': [], 'by_window': []}
        for lead, group in predictions.groupby('lead_hour'):
            stat = {'hour': int(lead), **metrics(group.actual.to_numpy(), group[name].to_numpy())}
            if name in report['intervals']:
                radius = report['intervals'][name][str(int(lead))]
                stat['coverage_pct'] = float((np.abs(group[name] - group.actual) <= radius).mean() * 100)
            result['by_lead'].append(stat)
        for horizon in [1, 6, 24]:
            group = predictions[predictions.lead_hour <= horizon]
            result['by_window'].append({'hours': horizon, **metrics(group.actual.to_numpy(), group[name].to_numpy())})
        report['models'][name] = result
    # A demo warning threshold, learned only from the final fitting period, not test peaks.
    report['peak_threshold_mw'] = float(data.loc[:VALID_END, 'load_mw'].quantile(.95))
    report['peak_threshold_note'] = '95th percentile of historical load through November 30, 2023; a research threshold, not grid capacity.'
    report['replay'] = {'min': test.origin.min().isoformat(), 'max': test.origin.max().isoformat(),
                        'default': test.origin.min().isoformat(), 'step_minutes': 60}
    daily_errors = predictions.groupby(predictions.origin.dt.date).apply(
        lambda g: pd.Series({'mae_mw': np.abs(g.weather-g.actual).mean(), 'baseline_mae_mw': np.abs(g.daily-g.actual).mean()}))
    report['daily_errors'] = [{'date': str(day), **row.to_dict()} for day, row in daily_errors.iterrows()]
    # Per-origin peak error evaluates each full 24-hour trajectory.
    errors = []
    for origin, group in predictions.groupby('origin'):
        pred_peak = group.loc[group.weather.idxmax()]
        true_peak = group.loc[group.actual.idxmax()]
        errors.append((abs(pred_peak.weather - true_peak.actual), abs(int(pred_peak.lead_hour) - int(true_peak.lead_hour))))
    report['peak_metrics'] = {'magnitude_mae_mw': float(np.mean([e[0] for e in errors])),
                              'timing_mae_hours': float(np.mean([e[1] for e in errors]))}
    (ARTIFACTS / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    predictions.to_csv(ARTIFACTS / 'test_predictions.csv', index=False)
    processed = ROOT / 'data' / 'processed'
    processed.mkdir(exist_ok=True)
    data.to_csv(processed / 'merged_hourly.csv')
    print('Saved models, evaluation, calibrated intervals, and merged data.', flush=True)


if __name__ == '__main__':
    main()
