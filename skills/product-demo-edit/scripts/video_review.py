#!/usr/bin/env python3
"""Read-only export checks and actual-file review frames. Requires ffmpeg/ffprobe."""
import argparse
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def probe(path):
    return json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_format', '-show_streams',
        '-of', 'json', str(path)], text=True))


def sample_times(times, ranges, duration, fps):
    step = 1 / fps
    selected = set()
    for value in times:
        if not math.isfinite(value) or not 0 <= value < duration:
            raise ValueError('Review time outside video: %s' % value)
        selected.add(value)
    for value in ranges:
        start, end = map(float, value.split(':'))
        if not (math.isfinite(start) and math.isfinite(end) and
                0 <= start < end <= duration):
            raise ValueError('Invalid seconds range: %s' % value)
        selected.update(max(0, min(duration - step, t)) for t in
                        (start - step, start, (start + end) / 2,
                         max(start, end - step), end, end + step))
    return sorted(set(round(t, 6) for t in selected))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('video', type=Path)
    p.add_argument('--out', required=True, type=Path, help='New, empty review directory')
    p.add_argument('--times', type=float, nargs='*', default=[])
    p.add_argument('--ranges', nargs='*', default=[], help='START:END in seconds')
    p.add_argument('--max-bytes', type=int, help='Strict upper bound, exclusive')
    p.add_argument('--width', type=int)
    p.add_argument('--height', type=int)
    p.add_argument('--fps', type=Fraction)
    p.add_argument('--duration', type=float)
    p.add_argument('--tolerance', type=float, default=0.1, help='Duration tolerance in seconds')
    p.add_argument('--decode', action='store_true')
    p.add_argument('--contact-sheet', action='store_true', help='Requires Pillow')
    args = p.parse_args()
    for name in ('ffprobe', 'ffmpeg'):
        if not shutil.which(name):
            p.error(name + ' is not on PATH')
    if not args.video.is_file():
        p.error('Input video does not exist')
    for key in ('max_bytes', 'width', 'height', 'fps', 'duration'):
        value = getattr(args, key)
        if value is not None and (not math.isfinite(float(value)) or value <= 0):
            p.error(key + ' must be positive and finite')
    if not math.isfinite(args.tolerance) or args.tolerance < 0:
        p.error('tolerance must be nonnegative and finite')
    if args.out.exists() and (not args.out.is_dir() or any(args.out.iterdir())):
        p.error('Use a new/empty review directory to preserve prior evidence')
    data = probe(args.video)
    videos = [s for s in data['streams'] if s['codec_type'] == 'video'
              and not s.get('disposition', {}).get('attached_pic')]
    if not videos:
        p.error('No video stream')
    v = videos[0]
    fps = float(Fraction(v.get('avg_frame_rate') or v['r_frame_rate']))
    duration = float(v.get('duration', data['format']['duration']))
    if fps <= 0 or duration <= 1 / fps:
        p.error('Invalid or too-short video duration/frame rate')
    times = sample_times(args.times, args.ranges, duration, fps)
    if args.contact_sheet:
        from PIL import Image, ImageDraw
    args.out.mkdir(parents=True, exist_ok=True)
    size = args.video.stat().st_size
    checks = {}
    for key in ('width', 'height'):
        expected = getattr(args, key)
        if expected is not None:
            checks[key] = v[key] == expected
    if args.fps is not None:
        checks['fps'] = abs(fps - float(args.fps)) < 0.001
    if args.duration is not None:
        checks['duration'] = abs(duration - args.duration) <= args.tolerance
    if args.max_bytes is not None:
        checks['size'] = size < args.max_bytes
    if args.decode:
        result = subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i',
                                 str(args.video), '-map', '0:v', '-map', '0:a?',
                                 '-f', 'null', '-'], capture_output=True, text=True)
        checks['decode'] = result.returncode == 0
        (args.out / 'decode.log').write_text(result.stderr, encoding='utf-8')
    frames = []
    for i, t in enumerate(times):
        target = args.out / ('frame-%03d-%010.4fs.png' % (i, t))
        subprocess.run(['ffmpeg', '-v', 'error', '-n', '-ss', str(t), '-i',
                        str(args.video), '-map', '0:%s' % v['index'],
                        '-frames:v', '1', str(target)], check=True)
        if not target.is_file() or not target.stat().st_size:
            raise RuntimeError('No frame extracted at %s' % t)
        frames.append({'seconds': t, 'file': target.name})
    if args.contact_sheet and frames:
        cell_w, cell_h = 480, 300
        sheet = Image.new('RGB', (cell_w * 3, cell_h * math.ceil(len(frames) / 3)), '#101923')
        draw = ImageDraw.Draw(sheet)
        for i, entry in enumerate(frames):
            with Image.open(args.out / entry['file']) as im:
                im.thumbnail((cell_w, cell_h - 30))
                x, y = (i % 3) * cell_w, (i // 3) * cell_h
                sheet.paste(im, (x, y + 25))
                draw.text((x + 8, y + 6), '%.4f s' % entry['seconds'], fill='white')
        sheet.save(args.out / 'contact-sheet.jpg', quality=90)
    report = {'input_name': args.video.name, 'sha256': sha256(args.video),
              'bytes': size, 'duration_seconds': duration, 'fps': fps,
              'width': v['width'], 'height': v['height'],
              'codecs': [s.get('codec_name') for s in data['streams']],
              'checks': checks, 'automated_checks_passed': all(checks.values()),
              'visual_review': 'pending', 'listening_review': 'pending', 'frames': frames}
    (args.out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        sys.exit(str(exc))
