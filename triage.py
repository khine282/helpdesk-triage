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
    is_it_issue: bool
    frustrated: bool
    priority: Literal["high", "medium", "low"]
    needs_more_info: bool
    # The ticket for the IT team, in English. "unknown" when the user has not said.
    title_en: str = Field(description="Short ticket title, at most 8 words")
    summary_en: str
    device: str = Field(description='"unknown" unless the user named the device or system')
    error_message: str = Field(description='The exact error text the user quoted. "unknown" unless the '
                                           'user mentioned an error message or explicitly said there is none')
    started: str = Field(description='"unknown" unless the user said when it started')
    tried_already: str = Field(description='"unknown" unless the user said what they tried')
    # Checked before writing questions, so no missing detail is forgotten
    missing_details: list[Literal["device", "problem", "error_message", "started", "tried_already"]]
    # The reply to the user, in clear parts, all in the user's language
    title_user: str = Field(description="The ticket title, in the user's language")
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
   Set is_it_issue to false only if it is clearly not an IT problem.
4. Detect whether the user sounds frustrated (true or false).
5. Using your reasoning from step 2, set priority: high if the user cannot
   work at all OR sounds frustrated, medium if work is slowed down, low otherwise.
   If the problem is still too vague to understand, use "low".
6. Set needs_more_info to true if IT could not start working on it yet because
   a key fact is missing: which device or system, or what exactly goes wrong.
7. Fill in the ticket for the IT team, in English:
   - title_en: a short title, e.g. "Laptop cannot connect to office Wi-Fi"
   - summary_en: the whole problem so far in one sentence
   - device, error_message (the exact words of the error, as the user gave
     them), started (when it started), tried_already (what the user already
     tried)
   Use only facts the user gave. Write "unknown" for anything not said. Never guess:
   a crash or a failure does not tell you whether an error message appeared.
   If the user says there is an error but not what it says, write "error shown,
   wording unknown". Only if the user explicitly answers that there is no error
   message, or that they don't know or didn't try anything, write exactly that
   (e.g. "none shown", "user doesn't know", "nothing yet"); these count as answered.
   Then set missing_details: every detail that is still "unknown" or "error
   shown, wording unknown", in this order: device, problem (what exactly goes
   wrong), error_message, started, tried_already. Leave it empty for a
   non-IT issue.
8. Write the reply to the user. title_user is the same short title as
   title_en, in the user's language. EVERY part (acknowledgement, each question,
   each try_now step, next_step) must be in the SAME language as the user's
   latest message. The examples below are in English only to show the idea;
   translate them. For "Mixed", use the main language of the message.
   - acknowledgement: one sentence that restates their specific problem, so
     they know you understood. If they sound frustrated, briefly show empathy.
   - questions: one question for each of the first 2 items in
     missing_details (so if missing_details is not empty, questions is not
     empty either). The rest are asked in later replies.
     Each question asks for ONE fact, can be answered in a few words, and
     gives example answers, e.g. "Which device is it: your office laptop,
     desktop PC, or phone?". Never ask a yes/no question: for the error, ask
     what it says, e.g. "What does the error message say? You can copy the
     text, or write 'no error' if there isn't one." Never ask for something
     the user already answered. Use an empty list only when every detail is
     answered, or the issue is not an IT issue.
   - try_now: up to 3 short, safe steps the user can try themselves, specific
     to their problem (e.g. restart the laptop, turn Wi-Fi off and on again,
     check the cable is plugged in). Never suggest anything risky: no changing
     system settings, installing software, or sharing passwords. Use an empty
     list if the problem is still unclear or not an IT issue.
   - next_step: one sentence. If needs_more_info is true, say you need their
     answer before passing the ticket to IT. Otherwise, if there are
     questions: "Your ticket has been passed to the IT team. Answering the
     questions above will help them fix it faster." If there are no
     questions: "Your ticket has been passed to the IT team." (translated)
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
        ticket = Ticket.model_validate_json(text).model_dump()
    except ValueError:
        return None
    return _ask_follow_ups(ticket)


# Fixed follow-up questions, used when the model forgets to ask for a missing detail
FOLLOW_UP_QUESTIONS = {
    "English": {
        "error_message": "What does the error message say? You can copy the text, or write 'no error' if there isn't one.",
        "started": "When did this start? For example: this morning, yesterday, or last week.",
        "tried_already": "What have you tried so far? For example: restarted it, or nothing yet.",
    },
    "Burmese": {
        "error_message": "Error message မှာ ဘာရေးထားလဲ? စာကို copy ကူးပေးလို့ရပါတယ်။ မရှိရင် 'မရှိ' လို့ ရေးပေးပါ။",
        "started": "ဒီပြဿနာ ဘယ်အချိန်ကစပြီး ဖြစ်တာလဲ? ဥပမာ - ဒီနေ့မနက်၊ မနေ့က၊ ပြီးခဲ့တဲ့အပတ်။",
        "tried_already": "ဘာတွေ စမ်းလုပ်ကြည့်ပြီးပြီလဲ? ဥပမာ - restart လုပ်ပြီးပြီ၊ ဒါမှမဟုတ် ဘာမှ မလုပ်ရသေးဘူး။",
    },
    "Chinese": {
        "error_message": "错误提示写的是什么？可以直接复制文字，如果没有请写“无”。",
        "started": "这个问题是什么时候开始的？例如：今天早上、昨天、或上周。",
        "tried_already": "您已经尝试过哪些方法？例如：重启过设备，或还没有尝试。",
    },
    "Malay": {
        "error_message": "Apakah mesej ralat yang dipaparkan? Anda boleh salin teksnya, atau tulis 'tiada' jika tiada.",
        "started": "Bilakah masalah ini bermula? Contohnya: pagi tadi, semalam, atau minggu lepas.",
        "tried_already": "Apakah yang telah anda cuba? Contohnya: mulakan semula, atau belum cuba apa-apa.",
    },
}
NOT_ANSWERED = ("", "unknown", "error shown, wording unknown")


def _ask_follow_ups(ticket):
    """The small model sometimes leaves a detail as "unknown" without asking about it.
    Check in code, and add the fixed question(s) so IT gets the full picture."""
    missing = [key for key in FOLLOW_UP_QUESTIONS["English"]
               if ticket[key].strip().lower() in NOT_ANSWERED]
    ticket["missing_details"] = [d for d in ticket["missing_details"] if d in ("device", "problem")] + missing
    if ticket["is_it_issue"] and not ticket["questions"] and missing:
        questions = FOLLOW_UP_QUESTIONS.get(ticket["language"], FOLLOW_UP_QUESTIONS["English"])
        ticket["questions"] = [questions[key] for key in missing[:2]]
    return ticket


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


# Plain questions for the details IT may still be missing, used in the contact email
DETAIL_QUESTIONS = {
    "error_message": "What exactly does the error message say?",
    "started": "When did the problem start?",
    "tried_already": "What have you already tried?",
}


class ContactEmail(BaseModel):
    subject: str
    body: str


def draft_contact_email(ticket, ticket_id, employee_name, employee_messages, on_status=_silent):
    """Draft an email from IT to the employee, in the employee's language, asking for a
    screenshot of the error and any details still missing. Returns {"subject", "body"}."""
    missing = [DETAIL_QUESTIONS[key] for key in FOLLOW_UP_QUESTIONS["English"]
               if ticket[key].strip().lower() in NOT_ANSWERED]
    prompt = f"""Write a short, polite email from the IT helpdesk team to an employee
about their ticket. Write it in {ticket["language"]}. If that is "Mixed" or "Other",
use the main language of the employee's messages below.
- Subject: the ticket number and the ticket title, translated.
- Body, with a blank line between each part:
  1. Greet the employee by name.
  2. One sentence saying IT is looking at the problem.
  3. Ask them to reply with a screenshot of the problem or error message.
  4. Only if this list is not empty, ask these questions, each on its own line
     starting with "- ", translated: {missing}
  5. Sign off as "IT Helpdesk".
- Do not promise how fast it will be fixed.
<ticket_number>{ticket_id}</ticket_number>
<employee_name>{employee_name}</employee_name>
<ticket>{json.dumps({"title": ticket["title_en"], "summary": ticket["summary_en"]}, ensure_ascii=False)}</ticket>
<employee_messages>{json.dumps(employee_messages, ensure_ascii=False)}</employee_messages>"""
    text = _call_model(prompt, "You write clear, friendly emails for an IT helpdesk.", on_status,
                       schema=ContactEmail)
    if text is None:
        return None
    try:
        return ContactEmail.model_validate_json(text).model_dump()
    except ValueError:
        return None


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    result = triage("ကျွန်တော့် ကွန်ပျူတာ အင်တာနက် ချိတ်လို့ မရဘူး")
    print(json.dumps(result, ensure_ascii=False, indent=2))