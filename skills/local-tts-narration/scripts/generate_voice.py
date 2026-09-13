#!/usr/bin/env python3
"""Resumable local IndexTTS 2.5 generation. Run inside the installed model environment."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import tempfile


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def key_for(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def atomic_json(path, value):
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     suffix='.tmp', delete=False) as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        temporary = Path(stream.name)
    os.replace(temporary, path)


def audio_duration(path):
    info = json.loads(subprocess.check_output(['ffprobe', '-v', 'error',
        '-show_format', '-show_streams', '-of', 'json', str(path)], text=True))
    seconds = float(info['format']['duration'])
    if not math.isfinite(seconds) or seconds <= 0 or not any(s['codec_type'] == 'audio' for s in info['streams']):
        raise ValueError('Invalid audio file')
    return seconds


def valid_cache(folder, key):
    try:
        meta = json.loads((folder / 'meta.json').read_text(encoding='utf-8'))
        audio = folder / 'audio.wav'
        return (meta['key'] == key and meta['sha256'] == digest(audio)
                and abs(meta['duration_seconds'] - audio_duration(audio)) < 0.001)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError):
        return False


def segments_from(manifest):
    segments = manifest['segments']
    if not isinstance(segments, list) or not segments:
        raise ValueError('segments must be a nonempty list')
    seen = set()
    for item in segments:
        name = item['id']
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', name) or name in seen:
            raise ValueError('Segment IDs must be unique safe file names')
        seen.add(name)
        if not isinstance(item['text'], str) or not item['text'].strip():
            raise ValueError('Empty segment text')
        if 'slot_seconds' in item and (not math.isfinite(item['slot_seconds']) or item['slot_seconds'] <= 0):
            raise ValueError('slot_seconds must be positive and finite')
    return segments


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest', type=Path)
    p.add_argument('--source', required=True, type=Path)
    p.add_argument('--model-dir', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--ids', nargs='+')
    p.add_argument('--plan', action='store_true', help='Do not import or load the model')
    args = p.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    segments = segments_from(manifest)
    source, models, output = args.source.resolve(), args.model_dir.resolve(), args.out.resolve()
    reference = (args.manifest.resolve().parent / manifest['reference']).resolve()
    if not manifest.get('model_id') or not manifest.get('reference_note'):
        p.error('Record model_id and reference_note in the manifest')
    if args.ids:
        unknown = set(args.ids) - {s['id'] for s in segments}
        if unknown:
            p.error('Unknown segment IDs: ' + ', '.join(sorted(unknown)))
        segments = [s for s in segments if s['id'] in args.ids]
    config = models / 'config.yaml'
    if not (source / 'indextts/infer_v2_5.py').is_file() or not config.is_file():
        p.error('IndexTTS 2.5 source or model config missing')
    audio_duration(reference)
    init = {'device': 'cpu', 'use_bf16': False, 'use_cuda_kernel': False, 'use_qwen_emo': False}
    init.update(manifest.get('init', {}))
    infer = {'lang': 'ZH', 'use_random': False, 'num_beams': 1}
    infer.update(manifest.get('inference', {}))
    if {'cfg_path', 'model_dir'} & set(init) or {'text', 'spk_audio_prompt', 'output_path'} & set(infer):
        p.error('Manifest must not override managed paths/text')
    seed = manifest.get('seed', 1234)
    common = {'model_id': manifest['model_id'], 'config_sha256': digest(config),
              'reference_sha256': digest(reference), 'script_sha256': digest(__file__),
              'source': {str(f.relative_to(source)): digest(f) for f in sorted((source / 'indextts').rglob('*.py'))},
              'model_files': {str(f.relative_to(models)): [f.stat().st_size, f.stat().st_mtime_ns]
                              for f in sorted(models.rglob('*')) if f.is_file()},
              'seed': seed, 'init': init, 'inference': infer}
    jobs = []
    for item in segments:
        key = key_for({'configuration': common, 'text': item['text']})
        folder = output / item['id'] / key
        jobs.append((item, key, folder, valid_cache(folder, key)))
    if args.plan:
        print(json.dumps([{'id': i['id'], 'key': k, 'cached': c} for i, k, _, c in jobs]))
        return 0
    output.mkdir(parents=True, exist_ok=True)
    run = {'complete_selection': False, 'all_segments_selected': not bool(args.ids), 'segments': []}
    atomic_json(output / 'run.json', run)
    tts = None
    for item, key, folder, cached in jobs:
        if not cached:
            if tts is None:
                os.chdir(source)
                sys.path.insert(0, str(source))
                import numpy as np
                import torch
                from indextts.infer_v2_5 import IndexTTS2
                tts = IndexTTS2(cfg_path=str(config), model_dir=str(models), **init)
            folder.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=folder) as temporary:
                audio = Path(temporary) / 'audio.wav'
                random.seed(seed)
                np.random.seed(seed)
                torch.manual_seed(seed)
                tts.infer(spk_audio_prompt=str(reference), text=item['text'], output_path=str(audio), **infer)
                seconds = audio_duration(audio)
                subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(audio),
                                '-f', 'null', '-'], check=True)
                meta = {'key': key, 'configuration': common, 'text': item['text'],
                        'reference_note': manifest['reference_note'], 'duration_seconds': seconds,
                        'sha256': digest(audio)}
                os.replace(audio, folder / 'audio.wav')
                atomic_json(folder / 'meta.json', meta)
        seconds = audio_duration(folder / 'audio.wav')
        run['segments'].append({'id': item['id'], 'key': key,
            'audio': str((folder / 'audio.wav').relative_to(output)), 'duration_seconds': seconds,
            'slot_seconds': item.get('slot_seconds'),
            'over_slot': seconds > item.get('slot_seconds', float('inf')), 'reused': cached})
        atomic_json(output / 'run.json', run)
        print(item['id'], 'cached' if cached else 'generated', round(seconds, 3), flush=True)
    run['complete_selection'] = True
    atomic_json(output / 'run.json', run)
    return 0


if __name__ == '__main__':
    sys.exit(main())
