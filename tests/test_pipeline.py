import io
import json
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from backend.app import app
from backend.grid.data import ARTIFACTS, TZ, feature_frame, prepare_data
from backend.grid.service import GridService, get_service


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.audit = prepare_data()
        cls.report = json.loads((ARTIFACTS/'report.json').read_text())
        cls.service = get_service()
        cls.client = TestClient(app)
        cls.origin = cls.report['replay']['default']

    def test_unit_conversion_and_all_hours_retained(self):
        self.assertAlmostEqual(self.data.iloc[0].load_mw, 138212.8)
        self.assertEqual(len(self.data), 11664)
        self.assertEqual(self.data.index[0].hour, 0)
        self.assertEqual(self.audit['missing_load_hours'], 0)
        self.assertEqual(self.audit['matched_rows'], 11662)

    def test_weather_alignment_is_backward_and_timezone_aware(self):
        known = self.data.dropna(subset=['weather_timestamp'])
        ages = pd.Series(known.index, index=known.index) - known.weather_timestamp
        self.assertTrue((ages == pd.Timedelta('30min')).all())
        self.assertEqual(str(self.data.index.tz), TZ)
        self.assertEqual(self.data.temperature_c.isna().sum(), 2)

    def test_features_do_not_change_when_future_values_change(self):
        origin = pd.Timestamp(self.origin)
        modified = self.data.copy()
        cols = ['load_mw', 'temperature_c', 'humidity_pct', 'rain_mm', 'wind_kmh']
        modified.loc[modified.index > origin, cols] = 999999
        for lead in [1, 6, 24]:
            expected = feature_frame(self.data, lead).loc[origin]
            actual = feature_frame(modified, lead).loc[origin]
            pd.testing.assert_series_equal(expected, actual)

    def test_split_boundaries_do_not_overlap_labels(self):
        s = self.report['splits']
        self.assertLess(pd.Timestamp(s['train']['target_end']), pd.Timestamp(s['validation']['origin_start']))
        self.assertLess(pd.Timestamp(s['validation']['target_end']), pd.Timestamp(s['calibration']['origin_start']))
        self.assertLess(pd.Timestamp(s['calibration']['target_end']), pd.Timestamp(s['test']['origin_start']))
        for name, params in self.report['parameters'].items():
            trials = [x['mae_mw'] for x in self.report['validation_trials'] if x['model']==name]
            self.assertEqual(params['mae_mw'], min(trials))

    def test_forecast_horizons_and_no_revealed_future(self):
        full = self.client.get('/api/forecast', params={'origin':self.origin,'horizon':24})
        self.assertEqual(full.status_code, 200, full.text)
        for horizon in [1,6,24]:
            response = self.client.get('/api/forecast', params={'origin':self.origin,'horizon':horizon})
            self.assertEqual(response.status_code,200,response.text)
            f = response.json()
            self.assertEqual(len(f['forecast']),horizon)
            self.assertEqual(f['forecast'],full.json()['forecast'][:horizon])
            self.assertTrue(all(pd.Timestamp(r['timestamp'])<=pd.Timestamp(self.origin) for r in f['history']))
            for i,r in enumerate(f['forecast'],1):
                self.assertNotIn('actual',r)
                self.assertEqual(pd.Timestamp(r['timestamp']),pd.Timestamp(self.origin)+pd.Timedelta(hours=i))
                self.assertTrue(np.isfinite(r['predicted_mw']))
                self.assertLessEqual(r['lower_mw'],r['predicted_mw'])
                self.assertGreaterEqual(r['upper_mw'],r['predicted_mw'])
            self.assertAlmostEqual(f['summary']['estimated_energy_mwh'],sum(x['predicted_mw'] for x in f['forecast']))

    def test_api_matches_saved_test_predictions(self):
        expected = pd.read_csv(ARTIFACTS/'test_predictions.csv')
        for model in ['weather','demand_only']:
            for origin in [self.origin, self.report['replay']['max']]:
                f = self.service.forecast(origin,24,model)
                rows = expected[expected.origin.map(pd.Timestamp)==pd.Timestamp(origin)].sort_values('lead_hour')
                np.testing.assert_allclose([r['predicted_mw'] for r in f['forecast']],rows[model].to_numpy(),atol=1e-6)

    def test_actuals_are_separate_and_match_source(self):
        response=self.client.get('/api/actuals',params={'origin':self.origin,'horizon':6})
        self.assertEqual(response.status_code,200,response.text)
        for row in response.json()['actuals']:
            self.assertAlmostEqual(row['load_mw'],self.data.loc[pd.Timestamp(row['timestamp']),'load_mw'])

    def test_invalid_dates_horizons_and_models_are_rejected(self):
        for params in [{'horizon':7},{'model':'unknown'},{'origin':'2022-02-01T00:00'},{'origin':'2024-04-30T23:00'},{'origin':'garbage'},{'origin':'2024-01-01T00:30'}]:
            response=self.client.get('/api/forecast',params=params)
            self.assertEqual(response.status_code,422,response.text)

    def test_history_pagination_filtering_and_csv_match(self):
        params={'start':'2024-02-01','end':'2024-02-01','page_size':12,'page':2}
        response=self.client.get('/api/history',params=params)
        self.assertEqual(response.status_code,200,response.text)
        body=response.json()
        self.assertEqual(body['total'],24)
        self.assertEqual(body['pages'],2)
        self.assertEqual(pd.Timestamp(body['rows'][0]['timestamp']).hour,12)
        csv=self.client.get('/api/history.csv',params=params)
        records=pd.read_csv(io.StringIO(csv.text))
        self.assertEqual(len(records),24)
        self.assertIn('unit_note',records.columns)
        empty=self.client.get('/api/history',params={'query':'NO RECORD'}).json()
        self.assertEqual(empty['rows'],[])
        self.assertEqual(self.client.get('/api/history',params={'start':'2024-04-01','end':'2024-03-01'}).status_code,422)

    def test_meta_evaluation_and_analytics(self):
        for endpoint in ['health','meta','evaluation','analytics']:
            response=self.client.get('/api/'+endpoint)
            self.assertEqual(response.status_code,200,response.text)
        a=self.client.get('/api/analytics').json()
        self.assertEqual(len(a['hourly']),24)
        self.assertEqual(len(a['heatmap']),42)

    def test_changed_source_requires_retraining(self):
        with patch('backend.grid.service.source_hashes',return_value={'changed':True}):
            with self.assertRaisesRegex(RuntimeError,'Source data changed'):
                GridService()


if __name__=='__main__':
    unittest.main()
