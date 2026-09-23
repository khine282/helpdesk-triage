import sys
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
client = genai.Client()
MODEL = "gemini-3.1-flash-lite"

SYSTEM = """You are an IT helpdesk triage assistant for a company with staff
in Singapore and Myanmar. The user's message is delimited by <message> tags.

Perform these steps:
1. Detect the language of the message.
2. Classify the issue as one of: hardware, network, account, software, other.
   If the message is not an IT issue, use "other".
3. Detect whether the user sounds frustrated (true or false).
4. Set priority: high if the user cannot work at all OR sounds frustrated,
   medium if work is slowed down, low otherwise.
5. Summarize the issue in one English sentence for the IT team.
6. Write a short, polite first reply in the SAME language the user wrote in.
   Acknowledge the specific problem. If it is not an IT issue, politely say
   this helpdesk only handles IT problems.
7. Do not promise fixes or timelines you cannot guarantee.

Example of a good Burmese reply:
<message>ပရင်တာ မထွက်ဘူး</message>
Reply: ပရင်တာ ပြဿနာအတွက် စိတ်မကောင်းပါဘူး။ IT အဖွဲ့ကို အကြောင်းကြားပြီးပါပြီ၊ မကြာခင် ဆက်သွယ်ပါလိမ့်မယ်။

Return ONLY a JSON object with keys: language, category, frustrated,
priority, summary_en, reply."""


def triage(message):
    response = client.models.generate_content(
        model=MODEL,
        contents=f"<message>{message}</message>",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM,
            temperature=0,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),

        ),
    )
    text = response.text
    text = text[text.find("{"): text.rfind("}") + 1]  # keep only the JSON part
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


# Quick test: runs only when you type "python triage.py"
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # so Burmese prints correctly on Windows
    result = triage("ကျွန်တော့် ကွန်ပျူတာ အင်တာနက် ချိတ်လို့ မရဘူး")
    print(json.dumps(result, ensure_ascii=False, indent=2))