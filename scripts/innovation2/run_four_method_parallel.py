"""Execute independent frozen videos in three processes; aggregate all attempts.

This changes scheduling only. Worker reports are internal partial snapshots;
the parent report is the sole full-dataset summary.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import multiprocessing
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.innovation2.run_four_method_accuracy import dump, sha, run, report, MODES
from src.knowledge.symbol_kb import SymbolKnowledgeBase


def worker(out_string, manifest):
    out = Path(out_string)
    # Transport timeout is not a model/generation parameter. Keep the original
    # frozen runner intact and explicitly record this scheduling override.
    import zai
    original_client = zai.ZhipuAiClient
    def client_with_longer_timeout(**kwargs):
        kwargs['timeout'] = 300
        return original_client(**kwargs)
    zai.ZhipuAiClient = client_with_longer_timeout
    api = out / 'api_calls.json'
    previous = json.loads(api.read_text()) if api.is_file() else []
    for c in previous:
        if 'status' not in c:
            c['status'] = 'interrupted'
    if previous:
        dump(out / 'api_calls_previous_attempts.json', previous)
    try:
        return run(out, manifest, SymbolKnowledgeBase())
    finally:
        new = json.loads(api.read_text()) if api.is_file() else []
        dump(api, previous + new)
        cfg_path = out / 'model_config.json'
        if cfg_path.is_file():
            cfg = json.loads(cfg_path.read_text())
            cfg['timeout_seconds'] = 300
            cfg['timeout_override'] = 'transport only; model, input and generation unchanged'
            dump(cfg_path, cfg)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', default='experiments/innovation2/results/four_method_accuracy_20261119')
    p.add_argument('--workers', type=int, default=3, choices=(1, 2, 3))
    a = p.parse_args()
    out = ROOT / a.output_dir
    manifest = json.loads((out / 'manifest.json').read_text())
    for name, expected in manifest['frozen_hashes'].items():
        if sha(ROOT / name) != expected:
            raise RuntimeError(f'Frozen input changed: {name}')
    for gt in manifest['items']:
        if sha(ROOT / gt['video_path']) != gt['video_sha256']:
            raise RuntimeError('Frozen video changed: ' + gt['video_id'])
    dump(out / 'execution_schedule.json', {'workers': a.workers, 'timeout_seconds': 300,
         'orchestrator_sha256': sha(__file__), 'changes': 'independent-video scheduling only',
         'primary_report': str(out / 'report.md'), 'worker_reports': 'internal partial snapshots'})
    previous_path = out / 'api_calls_before_parallel.json'
    if not previous_path.is_file():
        previous_path = out / 'api_calls.json'
    previous_calls = json.loads(previous_path.read_text()) if previous_path.is_file() else []
    for c in previous_calls:
        if 'status' not in c:
            c['status'] = 'interrupted'
    dump(out / 'api_calls_before_parallel.json', previous_calls)
    tasks = []
    for i in range(a.workers):
        wout = out / 'workers' / str(i)
        subset = dict(manifest, items=manifest['items'][i::a.workers])
        for gt in subset['items']:
            source = out / 'predictions' / gt['video_id']
            if source.is_dir():
                target = wout / 'predictions' / gt['video_id']
                target.mkdir(parents=True, exist_ok=True)
                for path in source.glob('*.json'):
                    dest = target / path.name
                    if not dest.is_file() or (json.loads(path.read_text()).get('status') == 'completed'
                            and json.loads(dest.read_text()).get('status') != 'completed'):
                        shutil.copy2(path, dest)
        tasks.append((wout, subset))
    kb = SymbolKnowledgeBase()
    with ProcessPoolExecutor(max_workers=a.workers, mp_context=multiprocessing.get_context('spawn')) as pool:
        futures = [pool.submit(worker, str(wout), subset) for wout, subset in tasks]
        while True:
            records, calls = [], list(previous_calls)
            for wout, subset in tasks:
                for gt in subset['items']:
                    for mode in MODES:
                        path = wout / 'predictions' / gt['video_id'] / (mode + '.json')
                        if path.is_file():
                            records.append(json.loads(path.read_text()))
                api = wout / 'api_calls.json'
                if api.is_file():
                    calls.extend(json.loads(api.read_text()))
            index = {g['video_id']: i for i, g in enumerate(manifest['items'])}
            records.sort(key=lambda r: (index[r['video_id']], MODES.index(r['mode'])))
            report(out, manifest, records, kb)
            dump(out / 'api_calls.json', calls)
            print('Completed:', sum(r['status'] == 'completed' for r in records), '/60 model annotations', flush=True)
            if all(f.done() for f in futures):
                for f in futures:
                    f.result()
                break
            time.sleep(5)


if __name__ == '__main__':
    main()
