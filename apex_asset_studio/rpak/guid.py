"""Slash-normalized case-insensitive asset hash."""
MASK32 = (1 << 32) - 1
MASK64 = (1 << 64) - 1


def string_to_guid(text: str) -> int:
    data = text.encode("utf-8") + b"\0" * 4
    state = 0
    i = 0
    while True:
        word = int.from_bytes(data[i:i + 4], "little")
        nulls = ((~word) & ((word - 0x01010101) & MASK32) & 0x80808080)
        mask = (nulls ^ ((nulls - 1) & MASK32)) & MASK32
        value = word & mask
        slash_bytes = sum(0x80 << shift for shift in (0, 8, 16, 24)
                          if (value >> shift) & 0xFF == 0x5C)
        value = ((value - 45 * (slash_bytes >> 7)) & MASK32) & 0xDFDFDFDF
        previous = (0x633D5F1 * state) & MASK64
        current = ((0xFB8C4D96501 * value) & MASK64) >> 24
        if nulls:
            length = i + (mask.bit_length() - 1) // 8
            return (current + previous - 0xAE502812AA7333 * length) & MASK64
        combined = (previous + current) & MASK64
        state = (combined >> 61) ^ combined
        i += 4


def guid_text(text: str) -> str:
    return f"{string_to_guid(text):016X}"
