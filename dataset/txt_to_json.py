#!/usr/bin/env python3
import json
import re
from pathlib import Path


BASE_DIR = Path("/data/data/xzy/CulturalVideoAnnotation")
INPUT_DIR = BASE_DIR / "outputs"
OUTPUT_FILE = BASE_DIR / "P-LS.json"
VIDEO_PREFIX = "/data/local-files/?d=xzy/CulturalVideoAnnotation/"
MODEL_VERSION = "Qwen3.5-9B"
DEFAULT_TEXT = "无法判断"

SECTION_MAP = {
    "E": "environment",
    "M": "main_subject",
    "C": "cultural",
    "A": "audiovisual",
    "S": "summary",
    "T": "technical",
}

SECTION_PATTERN = re.compile(
    r"【([EMCAST])｜[^】]+】\s*(.*?)(?=\n【[EMCAST]｜[^】]+】|\Z)",
    re.DOTALL,
)


def read_text_file(file_path: Path) -> str:
    last_error = None
    for encoding in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return file_path.read_text(encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise last_error if last_error else UnicodeDecodeError("unknown", b"", 0, 1, "decode failed")


def extract_video_path(content: str) -> str:
    match = re.search(r"^视频路径:\s*(.+?)\s*$", content, re.MULTILINE)
    return match.group(1).strip() if match else ""


def extract_sections(content: str) -> dict:
    sections = {key: DEFAULT_TEXT for key in SECTION_MAP}
    for match in SECTION_PATTERN.finditer(content):
        layer_key = match.group(1)
        layer_text = match.group(2).strip() or DEFAULT_TEXT
        sections[layer_key] = layer_text
    return sections


def build_result_item(from_name: str, text: str) -> dict:
    return {
        "from_name": from_name,
        "to_name": "video",
        "type": "textarea",
        "value": {
            "text": [text],
        },
    }


def convert_txt_to_task(file_path: Path) -> dict | None:
    content = read_text_file(file_path)
    video_path = extract_video_path(content)
    if not video_path:
        print(f"[SKIP] {file_path} 缺少视频路径")
        return None

    sections = extract_sections(content)
    results = [
        build_result_item(SECTION_MAP["E"], sections["E"]),
        build_result_item(SECTION_MAP["M"], sections["M"]),
        build_result_item(SECTION_MAP["C"], sections["C"]),
        build_result_item(SECTION_MAP["A"], sections["A"]),
        build_result_item(SECTION_MAP["S"], sections["S"]),
        build_result_item(SECTION_MAP["T"], sections["T"]),
    ]

    return {
        "data": {
            "video": f"{VIDEO_PREFIX}{video_path}",
        },
        "predictions": [
            {
                "model_version": MODEL_VERSION,
                "result": results,
            }
        ],
    }


def main() -> None:
    txt_files = sorted(path for path in INPUT_DIR.iterdir() if path.is_file() and path.suffix.lower() == ".txt")

    tasks = []
    skipped_count = 0

    for txt_file in txt_files:
        task = convert_txt_to_task(txt_file)
        if task is None:
            skipped_count += 1
            continue
        tasks.append(task)

    OUTPUT_FILE.write_text(
        json.dumps(tasks, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"读取到 {len(txt_files)} 个 txt")
    print(f"成功转换 {len(tasks)} 个")
    print(f"跳过 {skipped_count} 个")
    print(f"输出文件路径: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
