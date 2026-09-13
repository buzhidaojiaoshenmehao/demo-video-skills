"""Synthetic media and failure-path tests; no personal fixtures or model download."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
VOICE = ROOT / 'skills/local-tts-narration/scripts'
REVIEW = ROOT / 'skills/product-demo-edit/scripts/video_review.py'
sys.path.insert(0, str(VOICE))
from generate_voice import audio_duration, digest, key_for, segments_from, valid_cache
from align_narration import check_cues, srt_text


class CaptionTests(unittest.TestCase):
    def test_exact_script_and_overflow(self):
        cues = [{'text': '保存完成。', 'start': 0.2, 'end': 1.2}]
        check_cues(cues, '保存完成。', 2, 2)
        with self.assertRaises(ValueError):
            check_cues(cues, '保存失败。', 2, 2)
        with self.assertRaises(ValueError):
            check_cues(cues, '保存完成。', 2, 1)

    def test_overlap_and_nonfinite(self):
        for second in (0.9, float('nan')):
            with self.assertRaises(ValueError):
                check_cues([{'text': 'A', 'start': 0, 'end': 1},
                            {'text': 'B', 'start': second, 'end': 2}], 'AB', 3, 3)

    def test_srt_rounding_and_long_times(self):
        text = srt_text([{'text': 'A', 'start': 3661.123, 'end': 3662.456}])
        self.assertIn('01:01:01,123 --> 01:01:02,456', text)
        with self.assertRaises(ValueError):
            srt_text([{'text': 'A', 'start': 0.0001, 'end': 0.0002}])

    def test_safe_ids_and_parameter_cache_key(self):
        for segments in ([{'id': '../escape', 'text': 'A'}],
                         [{'id': 'same', 'text': 'A'}, {'id': 'same', 'text': 'B'}]):
            with self.assertRaises(ValueError):
                segments_from({'segments': segments})
        first = {'text': 'A', 'model_id': 'v1', 'temperature': 0.6}
        for name, value in [('text', 'B'), ('model_id', 'v2'), ('temperature', 0.7)]:
            self.assertNotEqual(key_for(first), key_for(dict(first, **{name: value})))


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg/ffprobe required')
class MediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.video = self.base / 'synthetic.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=320x180:rate=10:duration=2',
                        '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
                        str(self.video)], check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def review(self, name, *extra):
        return subprocess.run([sys.executable, str(REVIEW), str(self.video),
                               '--out', str(self.base / name), *extra],
                              capture_output=True, text=True)

    def test_export_checks_and_boundary_frames(self):
        before = digest(self.video)
        result = self.review('pass', '--width', '320', '--height', '180',
                             '--fps', '10', '--duration', '2', '--decode',
                             '--ranges', '0.3:1.5', '--times', '0', '1.9')
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads((self.base / 'pass/report.json').read_text())
        self.assertTrue(report['automated_checks_passed'])
        self.assertEqual(report['visual_review'], 'pending')
        times = {f['seconds'] for f in report['frames']}
        self.assertTrue({0, 0.2, 0.3, 0.9, 1.4, 1.5, 1.6, 1.9}.issubset(times))
        self.assertTrue(all((self.base / 'pass' / f['file']).stat().st_size for f in report['frames']))
        self.assertEqual(before, digest(self.video))

    def test_equal_limit_is_rejected(self):
        result = self.review('limit', '--max-bytes', str(self.video.stat().st_size))
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads((self.base / 'limit/report.json').read_text())['checks']['size'])

    def test_invalid_time_does_not_create_review(self):
        result = self.review('bad', '--times', '2.1')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.base / 'bad').exists())

    def test_preserve_existing_review(self):
        self.assertEqual(self.review('old').returncode, 0)
        old = digest(self.base / 'old/report.json')
        self.assertNotEqual(self.review('old').returncode, 0)
        self.assertEqual(digest(self.base / 'old/report.json'), old)

    def test_cache_corruption_is_detected(self):
        folder = self.base / 'voice'
        folder.mkdir()
        audio = folder / 'audio.wav'
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(self.video), '-vn',
                        str(audio)], check=True)
        meta = {'key': 'example', 'sha256': digest(audio), 'duration_seconds': audio_duration(audio)}
        (folder / 'meta.json').write_text(json.dumps(meta))
        self.assertTrue(valid_cache(folder, 'example'))
        self.assertFalse(valid_cache(folder, 'changed'))
        audio.write_bytes(b'not audio')
        self.assertFalse(valid_cache(folder, 'example'))


if __name__ == '__main__':
    unittest.main()
