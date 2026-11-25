"""Create one shared deterministic API representation per frozen video."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.innovation2.run_four_method_accuracy import dump, sha


def main():
    out = ROOT / 'experiments/innovation2/results/four_method_accuracy_20261119'
    manifest = json.loads((out / 'manifest.json').read_text())
    rows = []
    for g in manifest['items']:
        src = ROOT / g['video_path']
        dest = src
        if src.stat().st_size > 10 * 1024 * 1024:
            dest = out / 'api_inputs' / (g['video_id'] + '.mp4')
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.is_file():
                probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries',
                    'format=duration', '-of', 'json', str(src)]))
                duration = float(probe['format']['duration'])
                # Leave room for AAC, mux overhead and the encoder buffer.
                rate = max(64, int((8 * 1024 * 8) / duration) - 96)
                tmp = dest.with_suffix('.partial.mp4')
                subprocess.run(['ffmpeg', '-v', 'error', '-y', '-threads', '2', '-i', str(src),
                    '-map', '0:v:0', '-map', '0:a?', '-vf', "scale=w='min(1280,iw)':h=-2",
                    '-c:v', 'libx264', '-threads', '2', '-preset', 'veryfast',
                    '-b:v', f'{rate}k', '-maxrate', f'{rate}k', '-bufsize', f'{rate}k',
                    '-c:a', 'aac', '-b:a', '64k', '-movflags', '+faststart', str(tmp)], check=True)
                tmp.replace(dest)
            if dest.stat().st_size > 10 * 1024 * 1024:
                raise RuntimeError('Encoded video exceeds the common transport budget: ' + g['video_id'])
        rows.append({'video_id': g['video_id'], 'original_path': g['video_path'],
                     'original_sha256': g['video_sha256'], 'api_path': str(dest.relative_to(ROOT)),
                     'api_sha256': sha(dest), 'api_bytes': dest.stat().st_size,
                     'compressed': dest != src})
        print(g['video_id'], rows[-1]['api_bytes'], flush=True)
    dump(out / 'api_input_manifest.json', {'purpose': 'Identical encoded bytes for all methods of each video',
         'policy': 'Original <=10MiB; otherwise same deterministic H264/AAC representation, max width1280, unchanged timeline',
         'preprocessor_sha256': sha(__file__), 'items': rows})


if __name__ == '__main__':
    main()
