import sys
import json
import time
import httpx
from typing import Literal
from pydantic import BaseModel, Field
from google import genai
from google.genai import types, errors
from dotenv import load_dotenv

load_dotenv()
# Give up on a hung request after 20 seconds (value is in milliseconds)
client = genai.Client(http_options=types.HttpOptions(timeout=20_000))

# Tried in order: if one is busy or unavailable, the next one is used.
# Lite models chosen after testing: ~1-3s and reliable, while the bigger
# flash models were often busy (503) or took 10-17s.
MODELS = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]


class Ticket(BaseModel):
    """JSON mode: the model must answer with exactly these fields and values.
    Field order matters: reasoning comes before category and priority."""
    language: Literal["English", "Burmese", "Chinese", "Malay", "Mixed", "Other"]
    reasoning: str
    category: Literal["hardware", "network", "account", "software", "other"]
    frustrated: bool
    priority: Literal["high", "medium", "low"]
    needs_more_info: bool
    # The ticket for the IT team, in English. "unknown" when the user has not said.
    title_en: str = Field(description="Short ticket title, at most 8 words")
    summary_en: str
    device: str
    error_message: str
    started: str
    tried_already: str
    # The reply to the user, in clear parts, all in the user's language
    acknowledgement: str = Field(description="In the user's language")
    questions: list[str] = Field(description="Each item in the user's language")
    try_now: list[str] = Field(description="Each item in the user's language")
    next_step: str = Field(description="In the user's language")


SYSTEM = """You are the first-line IT helpdesk assistant for a company with
staff in Singapore and Myanmar. You will receive a conversation. Each user
message is delimited by <message> tags. Use ALL of the user's messages
together, because later messages may add details the user left out earlier.

Perform these steps in order:
1. Detect the language of the user's latest message. Use "Mixed" if it
   mixes languages, and "Other" for any language not in the list.
2. Before deciding anything else, work out your own reasoning: in one or two
   English sentences, explain what the problem is and how much it blocks the
   user's work. Do not decide the category or priority until you have done this.
3. Classify the issue as one of: hardware, network, account, software, other.
   If it is not an IT issue, or still too vague to classify, use "other".
4. Detect whether the user sounds frustrated (true or false).
5. Using your reasoning from step 2, set priority: high if the user cannot
   work at all OR sounds frustrated, medium if work is slowed down, low otherwise.
   If the problem is still too vague to understand, use "low".
6. Set needs_more_info to true if IT could not start working on it yet because
   a key fact is missing: which device or system, or what exactly goes wrong.
7. Fill in the ticket for the IT team, in English:
   - title_en: a short title, e.g. "Laptop cannot connect to office Wi-Fi"
   - summary_en: the whole problem so far in one sentence
   - device, error_message, started (when it started), tried_already (what
     the user already tried)
   Use only facts the user gave. Write "unknown" for anything not said. Never guess.
8. Write the reply to the user. EVERY part (acknowledgement, each question,
   each try_now step, next_step) must be in the SAME language as the user's
   latest message. The examples below are in English only to show the idea;
   translate them. For "Mixed", use the main language of the message.
   - acknowledgement: one sentence that restates their specific problem, so
     they know you understood. If they sound frustrated, briefly show empathy.
   - questions: at most 2, most important first, only for facts IT needs that
     are still unknown. Each question asks for ONE fact, can be answered in a
     few words, and gives example answers, e.g. "Which device is it: your
     office laptop, desktop PC, or phone?". Never ask for something the user
     already told you. Use an empty list if nothing important is missing.
   - try_now: up to 3 short, safe steps the user can try themselves, specific
     to their problem (e.g. restart the laptop, turn Wi-Fi off and on again,
     check the cable is plugged in). Never suggest anything risky: no changing
     system settings, installing software, or sharing passwords. Use an empty
     list if the problem is still unclear or not an IT issue.
   - next_step: one sentence. If needs_more_info is true, say you need their
     answer before passing the ticket to IT. Otherwise, say the ticket has
     been passed to the IT team.
9. If it is not an IT issue: priority low, needs_more_info false, questions
   and try_now empty, the acknowledgement politely says this helpdesk only
   handles IT problems, and next_step kindly suggests asking the right team
   (for example HR or office admin).
10. Do not promise fixes or timelines you cannot guarantee. Never say how fast
   IT will respond (no "immediately", "right away", "soon", or "within X minutes").

Example of natural Burmese wording for an acknowledgement:
ပရင်တာ ပြဿနာအတွက် စိတ်မကောင်းပါဘူး။"""


def _silent(message):
    pass


def _call_model(contents, system, on_status=_silent, schema=None):
    """Try each model once; move on straight away if one is busy, slow, or unavailable.
    on_status receives short progress messages so the UI can show what is happening.
    If schema is given, JSON mode is on and the answer must match it."""
    for i, model in enumerate(MODELS):
        if i > 0:
            on_status("Trying again with our backup assistant...")
        else:
            on_status("Analysing your issue...")
        start = time.perf_counter()
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=0,
                    response_mime_type="application/json" if schema else None,
                    response_schema=schema,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
            elapsed = time.perf_counter() - start
            on_status(f"Analysis finished in {elapsed:.1f}s")
            return response.text
        except errors.APIError as e:
            print(f"{model} failed ({e.code}) after {time.perf_counter() - start:.1f}s")
            on_status("The assistant is busy right now")
        except httpx.TimeoutException:
            print(f"{model} timed out, switching model")
            on_status("The assistant is taking too long")
    return None


def triage(history, on_status=_silent):
    """history is a list of turns: {"role": "user" or "model", "text": "..."}.
    A plain string also works, for single messages (used by eval.py).
    on_status is called with progress messages (the app shows them live)."""
    if isinstance(history, str):
        history = [{"role": "user", "text": history}]

    # The model has no memory, so we resend the whole conversation every time
    contents = []
    for turn in history:
        text = turn["text"]
        if turn["role"] == "user":
            text = f"<message>{text}</message>"
        contents.append(types.Content(role=turn["role"], parts=[types.Part(text=text)]))

    on_status("Reading your message")
    text = _call_model(contents, SYSTEM, on_status, schema=Ticket)
    if text is None:
        return None
    on_status("Preparing your ticket")
    # JSON mode means the answer is already clean JSON; still check it fits
    try:
        return Ticket.model_validate_json(text).model_dump()
    except ValueError:
        return None


def ticket_to_html(ticket, on_status=_silent):
    """Format conversion: turn the JSON ticket into an HTML email for IT."""
    prompt = f"""Convert the JSON ticket delimited by <ticket> tags into an HTML
email for the IT team. Include a short title, a one-line greeting, and a table
with one row per field (column headers: Field, Value). Keep the reply text in
its original language. Return ONLY the HTML.
<ticket>{json.dumps(ticket, ensure_ascii=False)}</ticket>"""
    html = _call_model(prompt, "You convert data between formats accurately.", on_status)
    if html is None:
        return None
    return html[html.find("<"): html.rfind(">") + 1]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    result = triage("ကျွန်တော့် ကွန်ပျူတာ အင်တာနက် ချိတ်လို့ မရဘူး")
    print(json.dumps(result, ensure_ascii=False, indent=2))