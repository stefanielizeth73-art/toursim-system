import base64
import heapq
import itertools
import json
from collections import defaultdict


def pack_varints(values):
    output = bytearray()
    for value in values:
        value = int(value)
        while True:
            to_write = value & 0x7F
            value >>= 7
            if value:
                output.append(to_write | 0x80)
            else:
                output.append(to_write)
                break
    return bytes(output)


def unpack_varints(payload):
    values = []
    current = 0
    shift = 0
    for byte in payload:
        current |= (byte & 0x7F) << shift
        if byte & 0x80:
            shift += 7
            continue
        values.append(current)
        current = 0
        shift = 0
    return values


def build_huffman_codes(byte_payload):
    if not byte_payload:
        return {0: "0"}

    frequencies = defaultdict(int)
    for byte in byte_payload:
        frequencies[byte] += 1

    heap = []
    counter = itertools.count()
    for byte_value, frequency in frequencies.items():
        heapq.heappush(heap, (frequency, next(counter), byte_value))

    if len(heap) == 1:
        return {heap[0][2]: "0"}

    while len(heap) > 1:
        left = heapq.heappop(heap)
        right = heapq.heappop(heap)
        heapq.heappush(heap, (left[0] + right[0], next(counter), (left[2], right[2])))

    root = heap[0][2]
    codes = {}

    def walk(node, prefix):
        if isinstance(node, int):
            codes[node] = prefix or "0"
            return
        left, right = node
        walk(left, prefix + "0")
        walk(right, prefix + "1")

    walk(root, "")
    return codes


def huffman_compress_text(text):
    raw_bytes = text.encode("utf-8")
    if not raw_bytes:
        package = {
            "algorithm": "huffman",
            "bit_length": 0,
            "payload_b64": "",
            "codes": {},
        }
        return package, 0, 0

    codes = build_huffman_codes(raw_bytes)
    bit_stream = "".join(codes[byte] for byte in raw_bytes)
    padded_bits = bit_stream + ("0" * ((8 - len(bit_stream) % 8) % 8))
    compressed_bytes = bytes(int(padded_bits[i:i + 8], 2) for i in range(0, len(padded_bits), 8)) if padded_bits else b""
    reverse_codes = {code: byte_value for byte_value, code in codes.items()}

    decoded_bits = "".join(f"{byte:08b}" for byte in compressed_bytes)[:len(bit_stream)]
    restored = bytearray()
    buffer = ""
    for bit in decoded_bits:
        buffer += bit
        if buffer in reverse_codes:
            restored.append(reverse_codes[buffer])
            buffer = ""

    if restored.decode("utf-8") != text:
        raise ValueError("Huffman 鍘嬬缉鏍￠獙澶辫触")

    package = {
        "algorithm": "huffman",
        "bit_length": len(bit_stream),
        "payload_b64": base64.b64encode(compressed_bytes).decode("ascii"),
        "codes": {str(byte_value): code for byte_value, code in codes.items()},
    }
    return package, len(raw_bytes), len(compressed_bytes)


def huffman_decompress_text(package):
    payload = base64.b64decode(package.get("payload_b64", "") or "")
    bit_length = int(package.get("bit_length", 0) or 0)
    codes = {code: int(byte_value) for byte_value, code in package.get("codes", {}).items()}
    if not payload or bit_length == 0:
        return ""

    bit_stream = "".join(f"{byte:08b}" for byte in payload)[:bit_length]
    restored = bytearray()
    buffer = ""
    for bit in bit_stream:
        buffer += bit
        if buffer in codes:
            restored.append(codes[buffer])
            buffer = ""
    return restored.decode("utf-8")


def lzw_compress_text(text):
    raw_bytes = text.encode("utf-8")
    if not raw_bytes:
        package = {
            "algorithm": "dictionary",
            "payload_b64": "",
            "code_count": 0,
        }
        return package, 0, 0

    dictionary = {bytes([byte_value]): byte_value for byte_value in range(256)}
    next_code = 256
    current = b""
    codes = []
    for byte in raw_bytes:
        candidate = current + bytes([byte])
        if candidate in dictionary:
            current = candidate
            continue
        if current:
            codes.append(dictionary[current])
        dictionary[candidate] = next_code
        next_code += 1
        current = bytes([byte])
    if current:
        codes.append(dictionary[current])

    packed = pack_varints(codes)
    restored = lzw_decompress_text({
        "payload_b64": base64.b64encode(packed).decode("ascii"),
    })
    if restored != text:
        raise ValueError("瀛楀吀鍘嬬缉鏍￠獙澶辫触")

    package = {
        "algorithm": "dictionary",
        "payload_b64": base64.b64encode(packed).decode("ascii"),
        "code_count": len(codes),
    }
    return package, len(raw_bytes), len(packed)


def lzw_decompress_text(package):
    payload = base64.b64decode(package.get("payload_b64", "") or "")
    if not payload:
        return ""

    codes = unpack_varints(payload)
    dictionary = {code: bytes([code]) for code in range(256)}
    next_code = 256
    decoded = bytearray()

    first_code = codes[0]
    if first_code not in dictionary:
        raise ValueError("瀛楀吀鍘嬬缉鏁版嵁鎹熷潖")
    current_entry = dictionary[first_code]
    decoded.extend(current_entry)

    for code in codes[1:]:
        if code in dictionary:
            entry = dictionary[code]
        elif code == next_code:
            entry = current_entry + current_entry[:1]
        else:
            raise ValueError("瀛楀吀鍘嬬缉鏁版嵁鎹熷潖")

        decoded.extend(entry)
        dictionary[next_code] = current_entry + entry[:1]
        next_code += 1
        current_entry = entry

    return decoded.decode("utf-8")


def compress_diary_text(text, algorithm):
    algorithm = (algorithm or "huffman").lower()
    if algorithm == "dictionary":
        package, original_length, compressed_length = lzw_compress_text(text)
    else:
        package, original_length, compressed_length = huffman_compress_text(text)
        algorithm = "huffman"

    package["algorithm"] = algorithm
    return package, original_length, compressed_length


def parse_diary_package(raw_value):
    if not raw_value:
        return None
    try:
        return json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        return None
