import json
import os
import time


def ensure_parent_dir(file_path):
    directory = os.path.dirname(file_path)
    if directory:
        os.makedirs(directory, exist_ok=True)


def write_json_atomic(file_path, payload):
    ensure_parent_dir(file_path)
    temp_path = f"{file_path}.{os.getpid()}.{int(time.time() * 1000000)}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    last_error = None
    for attempt in range(8):
        try:
            os.replace(temp_path, file_path)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.05 * (attempt + 1))
    try:
        os.remove(temp_path)
    except OSError:
        pass
    raise last_error


def read_json_file(file_path, default):
    if not os.path.exists(file_path):
        write_json_atomic(file_path, default)
        return default
    with open(file_path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def file_signature(path):
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return (int(stat.st_mtime_ns), int(stat.st_size))


def files_signature(paths):
    return tuple((path, file_signature(path)) for path in paths)
