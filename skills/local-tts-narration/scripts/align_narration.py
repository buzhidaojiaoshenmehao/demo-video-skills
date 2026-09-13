#!/usr/bin/env python3
"""Force-align final local narration and write complete, validated SRT/JSON."""
import argparse
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from generate_voice import atomic_json, audio_duration, digest, key_for, segments_from


def normalized(text):
    return re.sub(r'\s+', '', text)


def check_cues(cues, text, duration, slot):
    if not cues or normalized(''.join(c['text'] for c in cues)) != normalized(text):
        raise ValueError('Caption text does not match the approved script')
    previous = 0.0
    for cue in cues:
        start, end = cue['start'], cue['end']
        if not all(math.isfinite(t) for t in (start, end)):
            raise ValueError('Non-finite caption time')
        if not (previous <= start < end <= min(duration + 0.02, slot)):
            raise ValueError('Caption overlap or audio/slot overflow')
        previous = end


def milliseconds(seconds):
    return round(seconds * 1000)


def timestamp(ms):
    return '%02d:%02d:%02d,%03d' % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)


def srt_text(cues):
    rows, previous = [], 0
    for i, cue in enumerate(cues, 1):
        start, end = milliseconds(cue['start']), milliseconds(cue['end'])
        if not 0 <= previous <= start < end:
            raise ValueError('Global captions overlap or collapse at millisecond precision')
        previous = end
        rows.append('%d\n%s --> %s\n%s' % (i, timestamp(start), timestamp(end), cue['text']))
    return '\n\n'.join(rows) + '\n'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest', type=Path)
    p.add_argument('--model', type=Path, required=True, help='Existing local Whisper .pt file')
    p.add_argument('--device', default='cpu')
    p.add_argument('--out', type=Path, required=True, help='Versioned output directory; completed output is not overwritten')
    args = p.parse_args()
    if not args.model.is_file():
        p.error('A local model file is required')
    output = args.out.resolve()
    if (output / 'captions.json').exists():
        p.error('Completed output exists: choose a new version directory')
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    segments = segments_from(manifest)
    language = manifest.get('language', 'zh')
    model_path = args.model.resolve()
    model_key = digest(model_path)
    engine = version('stable-ts')
    output.mkdir(parents=True, exist_ok=True)
    cache = output / 'cache'
    cache.mkdir(exist_ok=True)
    all_cues, jobs = [], []
    for item in segments:
        start, slot = item['start_seconds'], item['slot_seconds']
        if not math.isfinite(start) or start < 0:
            p.error('start_seconds must be nonnegative and finite')
        audio = (args.manifest.resolve().parent / item['audio']).resolve()
        duration = audio_duration(audio)
        if duration > slot + 0.02:
            p.error('Audio exceeds slot for ' + item['id'] + '; adjust script/timeline before alignment')
        text = '\n'.join(re.findall(r'[^，。；！？,;!?\n]+[，。；！？,;!?]?', item['text']))
        parameters = {'audio_sha256': digest(audio), 'text': text, 'model_sha256': model_key,
                      'stable_ts': engine, 'script_sha256': digest(__file__),
                      'language': language, 'device': args.device,
                      'original_split': True, 'fast_mode': True}
        jobs.append((item, audio, duration, text, parameters, cache / (key_for(parameters) + '.json')))
    model = None
    for item, audio, duration, text, parameters, entry in jobs:
        cues = None
        if entry.exists():
            try:
                saved = json.loads(entry.read_text(encoding='utf-8'))
                if saved['parameters'] == parameters and saved['cues_sha256'] == key_for(saved['cues']):
                    check_cues(saved['cues'], item['text'], duration, item['slot_seconds'])
                    cues = saved['cues']
            except (OSError, ValueError, KeyError, TypeError):
                pass
        if cues is None:
            if model is None:
                import stable_whisper
                model = stable_whisper.load_model(str(model_path), device=args.device)
            result = model.align(str(audio), text, language=language,
                                 original_split=True, verbose=None, fast_mode=True)
            if result is None:
                raise ValueError('Alignment returned no result for ' + item['id'])
            cues = [{'text': s.text.strip(), 'start': s.start, 'end': s.end}
                    for s in result.segments if s.text.strip()]
            check_cues(cues, item['text'], duration, item['slot_seconds'])
            atomic_json(entry, {'parameters': parameters, 'cues': cues, 'cues_sha256': key_for(cues)})
        all_cues.extend({'id': item['id'], 'text': c['text'],
                         'start': item['start_seconds'] + c['start'],
                         'end': item['start_seconds'] + c['end']} for c in cues)
        print('aligned', item['id'], flush=True)
    all_cues.sort(key=lambda c: c['start'])
    srt = srt_text(all_cues)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=output,
                                     suffix='.tmp', delete=False) as stream:
        stream.write(srt)
        temporary = Path(stream.name)
    os.replace(temporary, output / 'captions.srt')
    atomic_json(output / 'captions.json', {'complete': True, 'cues': all_cues,
                'manifest_sha256': digest(args.manifest), 'listening_review': 'pending'})
    return 0


if __name__ == '__main__':
    sys.exit(main())
