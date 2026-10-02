export type ModelName = 'weather' | 'demand_only';
export type Horizon = 1 | 6 | 24;
export interface Audit {
  load_rows: number; weather_rows: number; matched_rows: number; unmatched_load_rows: number;
  duplicate_load_timestamps: number; missing_load_hours: number; load_start: string; load_end: string;
  overlap_start: string; overlap_end: string; load_min_mw: number; load_max_mw: number; load_mean_mw: number;
  weather_timezone: string; load_timezone: string; unit_assumption: string; unit_conversion: string;
  geographic_scope: string; weather_alignment: string; weather_use: string; load_timezone_assumption: string;
  source_url: string; provenance_note: string; source_hashes: Record<string,string>;
}
export interface Meta {
  audit: Audit; replay: { min: string; max: string; default: string; step_minutes: number };
  peak_threshold_mw: number; peak_threshold_note: string; trained_at: string; weather_note: string; interval_note: string;
}
export interface HistoryRow { timestamp: string; load_mw: number; load_w?: number; temperature_c?: number | null; humidity_pct?: number | null; rain_mm?: number | null; wind_kmh?: number | null; weather_timestamp?: string | null }
export interface ForecastRow { timestamp: string; lead: number; predicted_mw: number; lower_mw: number; upper_mw: number; baseline_mw: number; temperature_proxy_c: number; change_pct: number; risk: string }
export interface Forecast {
  origin: string; horizon: Horizon; model: ModelName; unit: string;
  summary: { current_mw: number; peak_mw: number; peak_time: string; average_mw: number; minimum_mw: number; estimated_energy_mwh: number; peak_change_pct: number };
  weather: { temperature_c: number; humidity_pct: number; rain_mm: number; wind_kmh: number; timestamp: string };
  history: HistoryRow[]; forecast: ForecastRow[]; threshold_mw: number; energy_note: string;
}
export interface Metric { mae_mw: number; rmse_mw: number; wape_pct: number; n: number }
export interface Evaluation {
  audit: Audit; models: Record<string, { overall: Metric; by_lead: (Metric & {hour: number; coverage_pct?: number})[]; by_window: (Metric & { hours: number })[] }>;
  splits: Record<string, { origin_start: string; origin_end: string; target_end: string; samples: number; origins: number }>;
  feature_importance: { feature: string; gain: number }[];
  daily_errors: { date: string; mae_mw: number; baseline_mae_mw: number }[];
  method: string; evaluation_note: string; development_note: string; weather_note: string; interval_note: string;
  peak_metrics: { magnitude_mae_mw: number; timing_mae_hours: number };
  parameters: Record<ModelName, {max_depth: number; trees: number; decay_hours: number; mae_mw: number}>;
  versions: Record<string,string>;
}
export interface Analytics {
  daily: { timestamp: string; average_mw: number; peak_mw: number }[];
  hourly: { hour: number; load_mw: number }[]; weekdays: { day: string; load_mw: number }[];
  heatmap: { day: number; block: number; load_mw: number }[];
  scatter: { temperature_c: number; load_mw: number }[]; temperature_correlation: number;
  climate: {
    temperature_bands: { band: string; average_mw: number; peak_mw: number; average_temperature_c: number; records: number }[];
    daily: { timestamp: string; average_temperature_c: number; average_mw: number; peak_mw: number }[];
    hot_days: { threshold_c: number; count: number; hot_average_mw: number; other_average_mw: number; difference_pct: number };
    controlled_temperature_mw_per_c: number; controlled_r2: number; controlled_note: string;
  };
}
export interface HistoryPage { rows: HistoryRow[]; total: number; page: number; pages: number; page_size: number }
export interface IndiaAnalytics {
  audit: { demand_rows: number; weather_rows: number; matched_rows: number; unmatched_rows: number; missing_demand_hours: number; demand_start: string; demand_end: string; demand_min_mw: number; demand_max_mw: number; demand_mean_mw: number; weather_coordinates: string; geography_note: string; unit_note: string };
  daily: { timestamp: string; average_mw: number; peak_mw: number }[];
  monthly: { timestamp: string; average_mw: number; peak_mw: number }[];
  hourly: { hour: number; load_mw: number }[];
  seasonal: { month: number; load_mw: number }[];
  scatter: { temperature_c: number; humidity_pct: number; load_mw: number }[];
  temperature_correlation: number | null;
}
