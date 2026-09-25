import json
import random
import streamlit as st
from triage import triage, ticket_to_html

st.set_page_config(page_title="IT Helpdesk Triage", page_icon="🛠️")
st.title("🛠️ Multilingual IT Helpdesk Triage")
st.caption("Chat in Burmese, English, Chinese, Malay, or a mix.")
st.info(
    "📚 Just a learning project. Try made-up examples like:\n\n"
    "- My laptop won't connect to the office Wi-Fi since this morning\n"
    "- Outlook crashes every time I open an attachment and I lost my work!!\n"
    "- ကွန်ပျူတာ အင်တာနက် ချိတ်လို့ မရဘူး\n"
    "- 我的打印机不能打印\n"
    "- Saya lupa kata laluan dan tidak boleh log masuk ke komputer"
)

# How each priority looks, and what it means in plain words
PRIORITY_STYLE = {
    "high": ("red", "🔴", "You can't work at all, or this is urgent. IT will look at it first."),
    "medium": ("orange", "🟠", "Your work is slowed down. IT will handle it after urgent issues."),
    "low": ("blue", "🔵", "A minor issue, or we still need more details from you."),
}
CATEGORY_ICON = {"hardware": "🖥️", "network": "📶", "account": "🔑", "software": "💾", "other": "❓"}

# Section headings in the bot's reply, in the user's language (English otherwise)
REPLY_LABELS = {
    "English": ("Please tell me:", "You can try this now:"),
    "Burmese": ("ကျေးဇူးပြု၍ ပြောပြပေးပါ -", "အခု စမ်းကြည့်နိုင်တာတွေ -"),
    "Chinese": ("请告诉我：", "您现在可以先试试："),
    "Malay": ("Sila beritahu saya:", "Anda boleh cuba sekarang:"),
}

# Ticket details IT needs, and how to label them in the ticket card
DETAILS = [("summary_en", "Problem"), ("device", "Device"), ("error_message", "Error message"),
           ("started", "Started"), ("tried_already", "Already tried")]


def ticket_badges(ticket):
    """Coloured tags for priority and category, e.g. [🔴 High priority] [📶 Network]."""
    priority = ticket["priority"].lower()
    color, dot, _ = PRIORITY_STYLE.get(priority, ("gray", "⚪", ""))
    category = ticket["category"].lower()
    icon = CATEGORY_ICON.get(category, "❓")
    return f":{color}-badge[{dot} {priority.title()} priority] :gray-badge[{icon} {category.title()}]"


def reply_markdown(ticket):
    """The bot's reply in clear parts: what we understood, questions, things to try, next step."""
    ask_label, try_label = REPLY_LABELS.get(ticket["language"], REPLY_LABELS["English"])
    parts = [ticket["acknowledgement"]]
    if ticket["questions"]:
        parts.append(f"**❓ {ask_label}**\n\n" + "\n".join(f"{i}. {q}" for i, q in enumerate(ticket["questions"], 1)))
    if ticket["try_now"]:
        parts.append(f"**🔧 {try_label}**\n\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(ticket["try_now"], 1)))
    parts.append(f"➡️ {ticket['next_step']}")
    return "\n\n".join(parts)


def detail_value(value):
    return "❓ *Not provided yet*" if value.strip().lower() in ("", "unknown") else value


# Memory: the conversation lives here and is resent to the model every turn
if "history" not in st.session_state:
    st.session_state.history = []
    st.session_state.ticket = None
    st.session_state.ticket_id = None

if st.button("🔄 Start a new ticket"):
    st.session_state.history = []
    st.session_state.ticket = None
    st.session_state.ticket_id = None
    st.rerun()

# Show the conversation so far
for turn in st.session_state.history:
    if turn["role"] == "user":
        st.chat_message("user").write(turn["text"])
    else:
        turn_ticket = json.loads(turn["text"])
        with st.chat_message("assistant"):
            st.markdown(reply_markdown(turn_ticket))
            st.markdown(ticket_badges(turn_ticket))

message = st.chat_input("Describe your IT issue, or answer the questions above")

if message:
    st.session_state.history.append({"role": "user", "text": message})
    st.chat_message("user").write(message)
    # Show each step live so the user can see the app is working, not stuck
    with st.status("Triaging your message...", expanded=True) as status:
        ticket = triage(st.session_state.history, on_status=st.write)
        if ticket is None:
            status.update(label="Could not triage your message", state="error")
        else:
            status.update(label="Ticket ready", state="complete", expanded=False)
    if ticket is None:
        st.session_state.history.pop()
        st.error("Sorry, the assistant could not process your message right now. Please send it again.")
        st.stop()
    st.session_state.history.append({"role": "model", "text": json.dumps(ticket, ensure_ascii=False)})
    st.session_state.ticket = ticket
    if st.session_state.ticket_id is None:
        st.session_state.ticket_id = f"HD-{random.randint(1000, 9999)}"
    st.rerun()

# Show the latest version of the ticket
ticket = st.session_state.ticket
if ticket:
    st.divider()
    st.subheader(f"🎫 Ticket {st.session_state.ticket_id}")
    st.caption("This is what gets sent to the IT team. It updates as you add details.")
    with st.container(border=True):
        st.markdown(f"#### {ticket['title_en']}")
        if ticket["needs_more_info"]:
            state = ":orange-badge[⏳ Waiting for your answer]"
        else:
            state = ":green-badge[✅ Ready for the IT team]"
        mood = ":orange-badge[😤 Sounds frustrated]" if ticket["frustrated"] else ""
        st.markdown(f"{state} {ticket_badges(ticket)} :gray-badge[🌐 {ticket['language']}] {mood}")
        meaning = PRIORITY_STYLE.get(ticket["priority"].lower(), ("", "", ""))[2]
        if meaning:
            st.markdown(f"**What this priority means:** {meaning}")

        st.markdown("**What IT knows so far**")
        rows = "\n".join(f"| **{label}** | {detail_value(ticket[key])} |" for key, label in DETAILS)
        st.markdown(f"| | |\n|---|---|\n{rows}")
        with st.expander("🧠 Why the AI chose this priority"):
            st.write(ticket["reasoning"])

    if st.button("📧 Convert ticket to an HTML email"):
        # Only the facts IT needs, not the chat reply
        for_it = {"ticket_id": st.session_state.ticket_id, "title": ticket["title_en"],
                  "priority": ticket["priority"], "category": ticket["category"],
                  "language": ticket["language"], "frustrated": ticket["frustrated"],
                  **{label: ticket[key] for key, label in DETAILS}}
        with st.status("Converting ticket to an HTML email...", expanded=True) as status:
            html = ticket_to_html(for_it, on_status=st.write)
            if html:
                status.update(label="Email ready", state="complete", expanded=False)
            else:
                status.update(label="Conversion failed", state="error")
        if html:
            st.markdown(html, unsafe_allow_html=True)
            with st.expander("See the HTML code"):
                st.code(html, language="html")
        else:
            st.error("Conversion failed. Please try again.")
