"""운영 DB와 외부 API 없이 검증·생성 안전장치를 검사한다."""
import contextlib
import copy
import io
import json
from pathlib import Path
import random
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_seed_sql as generator
import build_trails
import check_data
import check_selected
import data_contract as contract
import osm_trails

DATA = contract.ROOT / 'data'
SEEDS = contract.ROOT.parent / 'BE/src/main/resources/db/migration'


class DataContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.identity = contract.load_identity()
        cls.mountains = contract.read_csv(DATA / 'mountains.csv')
        cls.courses = contract.read_csv(DATA / 'courses.csv')
        cls.seed_mountains, cls.seed_courses = contract.load_seed(SEEDS)

    def test_existing_csv_and_seed_match_all_fields(self):
        report = contract.compare_seed(DATA, SEEDS)
        self.assertEqual((140, 420, 134), (report['mountains'], report['courses'], report['covered_mountains']))
        self.assertEqual({'쉬움': 115, '보통': 249, '어려움': 56}, report['difficulty'])
        self.assertEqual(36, len(report['endpoint_gap_over_30m']))

    def test_course_ids_do_not_depend_on_csv_order(self):
        rows = copy.deepcopy(self.courses)
        random.Random(21).shuffle(rows)
        self.assertEqual(contract.assign_course_ids(self.courses, self.identity),
                         contract.assign_course_ids(rows, self.identity))

    def test_scope_rejects_missing_duplicate_or_reassigned_mountains(self):
        for rows in [self.mountains[:-1], self.mountains + self.mountains[:1]]:
            with self.assertRaises(ValueError):
                contract.validate_scope(rows, self.courses, self.identity)
        rows = copy.deepcopy(self.mountains)
        rows[0]['name'], rows[1]['name'] = rows[1]['name'], rows[0]['name']
        with self.assertRaises(ValueError):
            contract.validate_scope(rows, self.courses, self.identity)

    def test_course_identity_drift_is_rejected(self):
        for field, value in [('name', '다른 이름'), ('source', 'other'), ('start_lat', '37.0'), ('mountain_id', '112')]:
            rows = copy.deepcopy(self.courses)
            rows[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                contract.assign_course_ids(rows, self.identity)
        for rows in [self.courses[:-1], self.courses + self.courses[:1]]:
            with self.assertRaises(ValueError):
                contract.assign_course_ids(rows, self.identity)

    def test_old_migration_changes_are_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in self.identity['seed_sha256']:
                shutil.copyfile(SEEDS / name, Path(folder) / name)
            with (Path(folder) / 'V3__courses.sql').open('a', encoding='utf-8') as stream:
                stream.write('\n')
            with self.assertRaisesRegex(ValueError, 'Flyway'):
                contract.compare_seed(DATA, folder)

    def test_course_attribute_drift_is_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ('mountains.csv', 'courses.csv', 'mountain_descriptions.csv'):
                shutil.copyfile(DATA / name, Path(folder) / name)
            path = Path(folder) / 'courses.csv'
            rows = contract.read_csv(path)
            rows[0]['difficulty'] = '쉬움' if rows[0]['difficulty'] != '쉬움' else '어려움'
            import csv
            with path.open('w', encoding='utf-8-sig', newline='') as stream:
                writer = csv.DictWriter(stream, rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(ValueError, '코스 CSV와 seed'):
                contract.compare_seed(folder, SEEDS)

    def test_difficulty_boundaries_and_missing_elevation_keep_existing_rule(self):
        cases = [(2.99, 199, '쉬움'), (3, 199, '보통'), (2, 200, '보통'),
                 (7.99, 599, '보통'), (8, 0, '어려움'), (1, 600, '어려움'),
                 (2.99, None, '쉬움'), (3, None, '보통'), (8, None, '어려움'), (1, 0, '쉬움')]
        for km, climb, expected in cases:
            with self.subTest(km=km, climb=climb):
                self.assertEqual(expected, build_trails.difficulty(km, climb))

    def test_csv_only_success_is_explicit(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(0, check_data.main(csv_only=True))
        self.assertIn('전체 데이터 검증 통과를 의미하지 않습니다', output.getvalue())

    def test_full_check_reports_missing_geojson_as_incomplete(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            for path in DATA.glob('*.csv'):
                shutil.copyfile(path, Path(folder) / path.name)
            shutil.copyfile(DATA / 'mountain_names.txt', Path(folder) / 'mountain_names.txt')
            self.assertEqual(2, check_data.main(data_dir=folder))

    def test_output_guard_rejects_data_migrations_and_nonempty_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            for path in (DATA, DATA / 'nested', SEEDS, out / 'BE/src/main/resources/db/migration'):
                with self.assertRaises(ValueError):
                    contract.require_empty_output(path, [DATA, SEEDS])
            (out / 'keep.txt').write_text('기존 파일', encoding='utf-8')
            with self.assertRaises(ValueError):
                contract.require_empty_output(out, [DATA])
            self.assertEqual('기존 파일', (out / 'keep.txt').read_text(encoding='utf-8'))

    def test_missing_geojson_writes_no_partial_sql(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(generator, 'DATA', Path(folder) / 'inputs'):
                generator.DATA.mkdir()
                for name in ('mountains.csv', 'courses.csv', 'mountain_descriptions.csv', 'trails.csv', 'mountain_names.txt'):
                    shutil.copyfile(DATA / name, generator.DATA / name)
                out = Path(folder) / 'candidate'
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, 'courses.geojson'):
                    generator.main(out)
                self.assertFalse(out.exists())

    def test_course_sql_has_explicit_stable_ids_and_is_deterministic(self):
        # 원본 대체 파일을 만들지 않고 기존 seed 경로를 직렬화 테스트의 메모리 입력으로만 사용한다.
        by_id = {r['id']: r for r in self.seed_courses}
        features = [{'properties': row, 'geometry': {'type': 'LineString', 'coordinates': json.loads(by_id[ident]['path'])}}
                    for ident, row in contract.assign_course_ids(self.courses, self.identity)]
        first = generator.courses_sql(features, self.identity)
        random.Random(21).shuffle(features)
        self.assertEqual(first, generator.courses_sql(features, self.identity))
        self.assertIn('INSERT INTO courses (id, mountain_id,', first)
        self.assertIn('RESTART WITH 421', first)
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'V2__mountains.sql').write_text(generator.mountains_sql(), encoding='utf-8')
            (Path(folder) / 'V3__courses.sql').write_text(first, encoding='utf-8')
            mountains, courses = contract.load_seed(folder)
            self.assertEqual(self.seed_mountains, mountains)
            for old, new in zip(self.seed_courses, courses):
                self.assertEqual({k: v for k, v in old.items() if k != 'path'}, {k: v for k, v in new.items() if k != 'path'})

    def test_geometry_rejects_empty_nonfinite_wrong_order_and_bad_endpoints(self):
        row = {'start_lat': '37.5', 'start_lon': '127.0'}
        mountain = {'summit_lat': '37.501', 'summit_lon': '127.001'}
        good = {'type': 'LineString', 'coordinates': [[127, 37.5], [127.001, 37.501]]}
        self.assertEqual(0, contract.validate_line(good, row, mountain))
        for coords in [[], [[127, 37.5]], [[127, float('nan')], [127, 37.5]],
                       [[37.5, 127], [37.501, 127.001]], [[127, 37.5, 1], [127, 37.501]],
                       [[True, 37.5], [127, 37.501]], [[127, 37.5], [127, 38.0]]]:
            with self.subTest(coords=coords), self.assertRaises(ValueError):
                contract.validate_line({'type': 'LineString', 'coordinates': coords}, row, mountain)

    def test_geojson_properties_must_match_csv(self):
        row = dict(self.courses[0])
        feature = {'properties': {**row, 'difficulty': '알 수 없음'}, 'geometry': {'type': 'LineString', 'coordinates': []}}
        with self.assertRaisesRegex(ValueError, '속성과 CSV'):
            contract.validate_features([feature], [row], {m['id']: m for m in self.mountains})

    def test_malformed_feature_is_reported_as_validation_error(self):
        row = dict(self.courses[0])
        for feature in [None, {'properties': None, 'geometry': {}}, {'properties': row, 'geometry': None}]:
            with self.subTest(feature=feature), self.assertRaises(ValueError):
                contract.validate_features([feature], [row], {})

    def test_selected_check_reports_missing_external_inputs(self):
        with patch.object(check_selected.os.path, 'isfile', return_value=False), contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as result:
                check_selected.main()
            self.assertEqual(2, result.exception.code)
            self.assertIn('provinces_geo.json', output.getvalue())
            self.assertIn('osm_peaks.json', output.getvalue())

    def test_osm_missing_cache_never_silently_becomes_no_courses(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(osm_trails, 'P', side_effect=lambda *parts: str(Path(folder).joinpath(*parts))), patch.object(osm_trails, 'ALLOW_NETWORK', False), patch.object(osm_trails.urllib.request, 'urlopen') as fetch:
            with self.assertRaises(FileNotFoundError):
                osm_trails.build(self.mountains[0], 1, 300, 0.3)
            fetch.assert_not_called()

    def test_osm_fetch_failure_aborts_instead_of_returning_empty_courses(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(osm_trails, 'P', side_effect=lambda *parts: str(Path(folder).joinpath(*parts))), patch.object(osm_trails, 'ALLOW_NETWORK', True), patch.object(osm_trails.urllib.request, 'urlopen', side_effect=OSError('테스트 수집 실패')), patch.object(osm_trails.time, 'sleep'), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, '수집에 실패'):
                osm_trails.fetch(self.mountains[0])

    def test_elevation_missing_cache_and_malformed_response_abort(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(build_trails, 'P', side_effect=lambda *parts: str(Path(folder).joinpath(*parts))), patch.object(osm_trails, 'ALLOW_NETWORK', False):
            with self.assertRaisesRegex(ValueError, '고도 캐시'):
                build_trails.elevations([(37.5, 127)])
        with tempfile.TemporaryDirectory() as folder, patch.object(build_trails, 'P', side_effect=lambda *parts: str(Path(folder).joinpath(*parts))), patch.object(osm_trails, 'ALLOW_NETWORK', True), patch.object(build_trails.urllib.request, 'urlopen', return_value=io.StringIO('{"elevation": []}')):
            with self.assertRaisesRegex(ValueError, '응답 개수'):
                build_trails.elevations([(37.5, 127)])

    def test_null_elevation_cache_preserves_missing_value_without_network(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'elevation_cache.json'
            path.write_text('{"37.50000,127.00000": null}', encoding='utf-8')
            before = path.read_bytes()
            with patch.object(build_trails, 'P', return_value=str(path)), patch.object(osm_trails, 'ALLOW_NETWORK', False):
                self.assertEqual({(37.5, 127): None}, build_trails.elevations([(37.5, 127)]))
            self.assertEqual(before, path.read_bytes())

    def test_missing_spot_zip_is_skipped(self):
        # 산림청이 산별 시종점 ZIP을 제공하지 않는 산이 있다. 없으면 건너뛰고 provenance에 기록한다.
        with tempfile.TemporaryDirectory() as folder, patch.object(build_trails, 'P', side_effect=lambda *parts: str(Path(folder).joinpath(*parts))):
            self.assertEqual([], build_trails.spot_trailheads(['missing']))


if __name__ == '__main__':
    unittest.main()
