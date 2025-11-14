#!/usr/bin/env python3

import sys
from pathlib import Path

# 添加父目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import convert_iso_to_mysql_datetime


def test_datetime_conversion():
    test_cases = [
        ("2025-03-18T01:57:54Z", "2025-03-18 01:57:54"),
        ("2023-12-01T15:30:45Z", "2023-12-01 15:30:45"),
        ("2024-01-15T00:00:00Z", "2024-01-15 00:00:00"),
        (None, None),
        ("", None),
        ("invalid", None),
    ]

    print("Testing datetime conversion:")
    for input_val, expected in test_cases:
        result = convert_iso_to_mysql_datetime(input_val)
        status = "✓" if result == expected else "✗"
        print(f"{status} Input: {input_val} -> Output: {result} (Expected: {expected})")


if __name__ == "__main__":
    test_datetime_conversion()
