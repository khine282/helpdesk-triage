import json
import random
import streamlit as st
from triage import Ticket, triage, ticket_to_html

st.set_page_config(page_title="IT Helpdesk Triage", page_icon="🛠️")
st.title("🛠️ Multilingual IT Helpdesk Triage")
st.caption("Chat in Burmese, English, Chinese, Malay, or a mix.")
st.info(
    "👤 **You are an employee** reporting an IT problem. The assistant asks for "
    "anything IT needs, suggests quick things to try, and opens a ticket. "
    "Pick a demo account in the sidebar.\n\n"
    "👩‍💻 Turn on **IT team view** to switch to the IT side and see the ticket they receive.\n\n"
    "📚 Just a learning project. Try made-up examples like:\n\n"
    "- My laptop won't connect to the office Wi-Fi since this morning\n"
    "- Outlook crashes every time I open an attachment and I lost my work!!\n"
    "- ကွန်ပျူတာ အင်တာနက် ချိတ်လို့ မရဘူး\n"
    "- 我的打印机不能打印\n"
    "- Saya lupa kata laluan dan tidak boleh log masuk ke komputer"
)

# How each priority looks, and what it means for the IT team
PRIORITY_STYLE = {
    "high": ("red", "🔴", "The employee can't work at all, or it's urgent. Handle first."),
    "medium": ("orange", "🟠", "The employee's work is slowed down. Handle after urgent tickets."),
    "low": ("blue", "🔵", "A minor issue, or still waiting for details from the employee."),
}
CATEGORY_ICON = {"hardware": "🖥️", "network": "📶", "account": "🔑", "software": "💾", "other": "❓"}

# Fixed wording in the bot's reply, in the user's language (English otherwise)
REPLY_LABELS = {
    "English": {"ask": "Please tell me:", "try": "You can try this now:", "created": "Ticket {id} created"},
    "Burmese": {"ask": "ကျေးဇူးပြု၍ ပြောပြပေးပါ -", "try": "အခု စမ်းကြည့်နိုင်တာတွေ -",
                "created": "Ticket {id} ဖွင့်ပြီးပါပြီ"},
    "Chinese": {"ask": "请告诉我：", "try": "您现在可以先试试：", "created": "已创建工单 {id}"},
    "Malay": {"ask": "Sila beritahu saya:", "try": "Anda boleh cuba sekarang:", "created": "Tiket {id} telah dibuka"},
}

# Ticket details IT needs, and how to label them in the ticket card
DETAILS = [("summary_en", "Problem"), ("device", "Device"), ("error_message", "Error message"),
           ("started", "Started"), ("tried_already", "Already tried")]
# IT can start without these, and the assistant keeps asking for them after the ticket is opened
FOLLOW_UP_DETAILS = {"error_message", "started", "tried_already"}

# Placeholder accounts. A real helpdesk would get these from the login system,
# so the employee never has to type who they are or which department they are in.
DEMO_USERS = {
    "EMP-1024": {"name": "Demo User 1", "department": "Finance", "office": "Singapore"},
    "EMP-2048": {"name": "Demo User 2", "department": "Operations", "office": "Yangon"},
    "EMP-4096": {"name": "Demo User 3", "department": "Sales", "office": "Singapore"},
}


def ticket_badges(ticket):
    """Coloured tags for priority and category, e.g. [🔴 High priority] [📶 Network]."""
    priority = ticket["priority"].lower()
    color, dot, _ = PRIORITY_STYLE.get(priority, ("gray", "⚪", ""))
    category = ticket["category"].lower()
    icon = CATEGORY_ICON.get(category, "❓")
    return f":{color}-badge[{dot} {priority.title()} priority] :gray-badge[{icon} {category.title()}]"


def is_ready(ticket):
    """The ticket can go to IT: it is an IT problem and nothing important is missing."""
    return ticket["is_it_issue"] and not ticket["needs_more_info"]


def reply_markdown(ticket):
    """The bot's reply in clear parts: what we understood, questions, things to try, next step."""
    labels = REPLY_LABELS.get(ticket["language"], REPLY_LABELS["English"])
    parts = [ticket["acknowledgement"]]
    if ticket["questions"]:
        parts.append(f"**❓ {labels['ask']}**\n\n" + "\n".join(f"{i}. {q}" for i, q in enumerate(ticket["questions"], 1)))
    if ticket["try_now"]:
        parts.append(f"**🔧 {labels['try']}**\n\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(ticket["try_now"], 1)))
    parts.append(f"➡️ {ticket['next_step']}")
    return "\n\n".join(parts)


def detail_value(key, value):
    if value.strip().lower() not in ("", "unknown"):
        return value
    return "⏳ *Not answered yet*" if key in FOLLOW_UP_DETAILS else "❓ *Not provided yet*"


def reporter_text(user_id):
    user = DEMO_USERS[user_id]
    return f"{user['name']} ({user_id}), {user['department']}, {user['office']} office"


def is_old_format(state):
    """A browser tab opened before an app update may hold a ticket without the current fields."""
    ticket = state.get("ticket")
    return "ticket_id" not in state or (ticket is not None and not set(Ticket.model_fields) <= set(ticket))


# Memory: the conversation lives here and is resent to the model every turn
if "history" not in st.session_state or is_old_format(st.session_state):
    st.session_state.history = []
    st.session_state.ticket = None
    st.session_state.ticket_id = None

user_id = st.sidebar.selectbox("🔐 Signed in as (demo account)", list(DEMO_USERS),
                               format_func=reporter_text)
st.sidebar.caption("Placeholder accounts. A real system would use the company login.")

col1, col2 = st.columns(2)
if col1.button("🔄 Start a new ticket"):
    st.session_state.history = []
    st.session_state.ticket = None
    st.session_state.ticket_id = None
    st.rerun()
it_view = col2.toggle("👩‍💻 IT team view", help="See the ticket the IT team receives, instead of the chat")


def show_employee_view():
    """The chat, as the employee sees it: replies and a ticket confirmation, nothing internal."""
    ticket_announced = False
    for turn in st.session_state.history:
        if turn["role"] == "user":
            st.chat_message("user").write(turn["text"])
            continue
        turn_ticket = json.loads(turn["text"])
        with st.chat_message("assistant"):
            st.markdown(reply_markdown(turn_ticket))
            # Tell the employee once, like a helpdesk confirmation email, when their ticket is opened
            if is_ready(turn_ticket) and not ticket_announced:
                labels = REPLY_LABELS.get(turn_ticket["language"], REPLY_LABELS["English"])
                created = labels["created"].format(id=st.session_state.ticket_id)
                st.success(f"✅ **{created}:** {turn_ticket['title_user']}")
                ticket_announced = True

    message = st.chat_input("Describe your IT problem, or answer the questions above")
    if not message:
        return
    st.session_state.history.append({"role": "user", "text": message})
    st.chat_message("user").write(message)
    # Show each step live so the user can see the app is working, not stuck
    with st.status("Working on your request...", expanded=True) as status:
        ticket = triage(st.session_state.history, on_status=st.write)
        if ticket is None:
            status.update(label="Could not process your message", state="error")
        else:
            status.update(label="Done", state="complete", expanded=False)
    if ticket is None:
        st.session_state.history.pop()
        st.error("Sorry, the assistant could not process your message right now. Please send it again.")
        st.stop()
    st.session_state.history.append({"role": "model", "text": json.dumps(ticket, ensure_ascii=False)})
    st.session_state.ticket = ticket
    if st.session_state.ticket_id is None:
        st.session_state.ticket_id = f"HD-{random.randint(1000, 9999)}"
    st.rerun()


def show_it_view():
    """The full ticket, as the IT team sees it. The employee does not see any of this."""
    ticket = st.session_state.ticket
    if not ticket:
        st.info("No ticket yet. Turn off IT team view and describe a problem as the employee first.")
        return
    st.subheader(f"🎫 Ticket {st.session_state.ticket_id}")
    st.caption("What the IT team receives. It updates as the employee adds details.")
    with st.container(border=True):
        st.markdown(f"#### {ticket['title_en']}")
        if not ticket["is_it_issue"]:
            state = ":gray-badge[🚫 Not an IT issue, no ticket needed]"
        elif ticket["needs_more_info"]:
            state = ":orange-badge[⏳ Waiting for the employee's answer]"
        else:
            state = ":green-badge[✅ Ready for the IT team]"
        mood = ":orange-badge[😤 Sounds frustrated]" if ticket["frustrated"] else ""
        st.markdown(f"{state} {ticket_badges(ticket)} :gray-badge[🌐 {ticket['language']}] {mood}")
        meaning = PRIORITY_STYLE.get(ticket["priority"].lower(), ("", "", ""))[2]
        if meaning:
            st.markdown(f"**What this priority means:** {meaning}")

        st.markdown("**Ticket details**")
        rows = [f"| **Reported by** | {reporter_text(user_id)} |"]
        rows += [f"| **{label}** | {detail_value(key, ticket[key])} |" for key, label in DETAILS]
        st.markdown("| | |\n|---|---|\n" + "\n".join(rows))
        with st.expander("🧠 Why the AI chose this priority"):
            st.write(ticket["reasoning"])
        with st.expander("💬 Conversation with the employee"):
            for turn in st.session_state.history:
                if turn["role"] == "user":
                    st.markdown(f"**Employee:** {turn['text']}")
                else:
                    turn_ticket = json.loads(turn["text"])
                    st.markdown(f"**Assistant:** {turn_ticket['acknowledgement']}  \n{ticket_badges(turn_ticket)}")

    if st.button("📧 Convert ticket to an HTML email"):
        # Only the facts IT needs, not the chat reply
        user = DEMO_USERS[user_id]
        for_it = {"ticket_id": st.session_state.ticket_id, "title": ticket["title_en"],
                  "reported_by": f"{user['name']} ({user_id})", "department": user["department"],
                  "office": user["office"], "priority": ticket["priority"], "category": ticket["category"],
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


if it_view:
    show_it_view()
else:
    show_employee_view()
