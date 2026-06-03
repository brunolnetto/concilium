"""Fix the backtick-n issue in test file."""
from pathlib import Path

f = Path("tests/unit/test_coverage_boost_main.py")
raw = f.read_bytes()

# Find the backtick character (0x60) followed by 'n' followed by 'def'
# and replace with newline + 'def'
backtick_n = bytes([0x60, 0x6e])  # `n
newline = bytes([0x0a])  # \n

# Replace `ndef with \ndef
fixed = raw.replace(backtick_n + b"def ", newline + b"def ")
f.write_bytes(fixed)

# Verify
remaining = fixed.count(backtick_n + b"def ")
print(f"Remaining `ndef occurrences: {remaining}")
print("Done!")
