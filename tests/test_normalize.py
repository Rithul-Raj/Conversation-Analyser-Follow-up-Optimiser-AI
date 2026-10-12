import sys
sys.path.insert(0, ".")
from services.database import _normalize_time_filter

tests = [
    ("7 pm",    "7:00 pm"),
    ("7pm",     "7:00 pm"),
    ("7 PM",    "7:00 pm"),
    ("7PM",     "7:00 pm"),
    ("7:00 PM", "7:00 pm"),
    ("7:00pm",  "7:00 pm"),
    ("7:30 PM", "7:30 pm"),
    ("7:30pm",  "7:30 pm"),
    ("11 AM",   "11:00 am"),
    ("morning", "morning"),
    ("Morning", "morning"),
]
all_ok = True
for raw, expected in tests:
    result = _normalize_time_filter(raw)
    ok = result == expected
    status = "OK  " if ok else "FAIL"
    print(f"  {status}  {raw!r:<12} -> {result!r:<14}  expected: {expected!r}")
    all_ok = all_ok and ok

print()
print("All passed." if all_ok else "SOME FAILED.")
