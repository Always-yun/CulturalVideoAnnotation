"""Same experiment with raw scene responses persisted before parsing.

Use a NEW --output-dir for a future run. This entrypoint changes no generation,
retrieval, parsing or retry rule, and cannot recover past missing responses.
"""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def audited_parse(raw, parser, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    body = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
    key = hashlib.sha256(body.encode('utf-8')).hexdigest()
    path = directory / (key + '.json')
    path.write_text(json.dumps({'raw_response': raw, 'sha256': key,
                               'persisted_before_parse': True}, ensure_ascii=False, indent=2), encoding='utf-8')
    return parser(raw)


def main():
    from scripts.innovation2 import run_four_method_accuracy as runner
    from src.pipeline import scene_evidence
    args = sys.argv[1:]
    if '--output-dir' not in args:
        raise SystemExit('Specify a NEW --output-dir to keep the completed frozen experiment unchanged.')
    out = ROOT / args[args.index('--output-dir') + 1]
    parser = scene_evidence.normalize_scene
    scene_evidence.normalize_scene = lambda raw: audited_parse(raw, parser, out / 'raw_scene_responses')
    runner.dump(out / 'raw_scene_audit_entrypoint.json', {'entrypoint_sha256': runner.sha(__file__),
        'policy': 'persist raw response before unchanged parser; no generation or retry change'})
    runner.main()


if __name__ == '__main__':
    main()
