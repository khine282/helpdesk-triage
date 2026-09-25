import sys
import json
import time
import httpx
from google import genai
from google.genai import types, errors
from dotenv import load_dotenv

load_dotenv()
# Give up on a hung request after 20 seconds (value is in milliseconds)
client = genai.Client(http_options=types.HttpOptions(timeout=20_000))

# Tried in order: if one is busy or unavailable, the next one is used
MODELS = ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash"]

SYSTEM = """You are an IT helpdesk triage assistant for a company with staff
in Singapore and Myanmar. You will receive a conversation. Each user message
is delimited by <message> tags. Use ALL of the user's messages together,
because later messages may add details the user left out earlier.

Perform these steps in order:
1. Detect the language of the user's latest message.
2. Before deciding anything else, work out your own reasoning: in one or two
   English sentences, explain what the problem is and how much it blocks the
   user's work. Do not decide the category or priority until you have done this.
3. Classify the issue as one of: hardware, network, account, software, other.
   If it is not an IT issue, use "other".
4. Detect whether the user sounds frustrated (true or false).
5. Using your reasoning from step 2, set priority: high if the user cannot
   work at all OR sounds frustrated, medium if work is slowed down, low otherwise.
6. Summarize the whole problem so far in one English sentence for the IT team.
7. Write a short, polite reply in the SAME language as the user's latest message.
   Acknowledge the specific problem. If it is still too vague to understand
   (for example, it does not say which device), set category to "other" and
   priority to "low", and ask ONE short clarifying question. If it is not an
   IT issue, politely say this helpdesk only handles IT problems.
8. Do not promise fixes or timelines you cannot guarantee.

Example of a good Burmese reply:
<message>ပရင်တာ မထွက်ဘူး</message>
Reply: ပရင်တာ ပြဿနာအတွက် စိတ်မကောင်းပါဘူး။ IT အဖွဲ့ကို အကြောင်းကြားပြီးပါပြီ၊ မကြာခင် ဆက်သွယ်ပါလိမ့်မယ်။

Return ONLY a JSON object with keys in this order: language, reasoning,
category, frustrated, priority, summary_en, reply."""


def _call_model(contents, system):
    """Try each model in order; move on if one is busy or unavailable."""
    for model in MODELS:
        for _ in range(2):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system,
                        temperature=0,
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                    ),
                )
                print(f"Answered by {model}")
                return response.text
            except errors.APIError as e:
                print(f"{model} failed ({e.code}), retrying...")
                time.sleep(3)
            except httpx.TimeoutException:
                print(f"{model} timed out, retrying...")
        print(f"Switching away from {model}")
    return None


def triage(history):
    """history is a list of turns: {"role": "user" or "model", "text": "..."}.
    A plain string also works, for single messages (used by eval.py)."""
    if isinstance(history, str):
        history = [{"role": "user", "text": history}]

    # The model has no memory, so we resend the whole conversation every time
    contents = []
    for turn in history:
        text = turn["text"]
        if turn["role"] == "user":
            text = f"<message>{text}</message>"
        contents.append(types.Content(role=turn["role"], parts=[types.Part(text=text)]))

    text = _call_model(contents, SYSTEM)
    if text is None:
        return None
    text = text[text.find("{"): text.rfind("}") + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def ticket_to_html(ticket):
    """Format conversion: turn the JSON ticket into an HTML email for IT."""
    prompt = f"""Convert the JSON ticket delimited by <ticket> tags into an HTML
email for the IT team. Include a short title, a one-line greeting, and a table
with one row per field (column headers: Field, Value). Keep the reply text in
its original language. Return ONLY the HTML.
<ticket>{json.dumps(ticket, ensure_ascii=False)}</ticket>"""
    html = _call_model(prompt, "You convert data between formats accurately.")
    if html is None:
        return None
    return html[html.find("<"): html.rfind(">") + 1]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    result = triage("ကျွန်တော့် ကွန်ပျူတာ အင်တာနက် ချိတ်လို့ မရဘူး")
    print(json.dumps(result, ensure_ascii=False, indent=2))