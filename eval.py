import sys
import time
from triage import triage

sys.stdout.reconfigure(encoding="utf-8")

# (message, expected category, expected priority)
tests = [
    ("ကျွန်တော့် ကွန်ပျူတာ အင်တာနက် ချိတ်လို့ မရဘူး", "network", "high"),
    ("စကားဝှက် မေ့သွားလို့ အကောင့်ဝင်လို့ မရဘူး", "account", "high"),
    ("Laptop က screen မှိတ်တုတ်မှိတ်တုတ် ဖြစ်နေတယ်", "hardware", "medium"),
    ("My mouse scroll wheel is a bit sticky", "hardware", "low"),
    ("Outlook crashes every time I open an attachment. This is the THIRD time today!!", "software", "high"),
    ("我的打印机不能打印", "hardware", "medium"),
    ("What time is lunch today?", "other", "low"),
    # add more of your own here
]

correct = 0
for msg, expected_cat, expected_pri in tests:
    result = triage(msg)
    if result is None:
        print("ERROR", msg)
    else:
        match = result["category"] == expected_cat and result["priority"] == expected_pri
        correct += match
        status = "OK  " if match else "MISS"
        print(f"{status} | {msg} | got: {result['category']}, {result['priority']}")
    time.sleep(6)  # stay under the free tier's requests-per-minute limit

print(f"\nAccuracy: {correct}/{len(tests)}")