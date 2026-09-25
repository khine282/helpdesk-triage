import json
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
    "medium": ("orange", "🟠", "Your work is slowed down. IT will pick it up soon."),
    "low": ("blue", "🔵", "A minor issue, or the bot still needs more detail from you."),
}
CATEGORY_ICON = {"hardware": "🖥️", "network": "📶", "account": "🔑", "software": "💾", "other": "❓"}


def ticket_badges(ticket):
    """Coloured tags for priority and category, e.g. [🔴 High priority] [📶 Network]."""
    priority = ticket["priority"].lower()
    color, dot, _ = PRIORITY_STYLE.get(priority, ("gray", "⚪", ""))
    category = ticket["category"].lower()
    icon = CATEGORY_ICON.get(category, "❓")
    return f":{color}-badge[{dot} {priority.title()} priority] :gray-badge[{icon} {category.title()}]"


# Memory: the conversation lives here and is resent to the model every turn
if "history" not in st.session_state:
    st.session_state.history = []
    st.session_state.ticket = None

if st.button("🔄 Start a new ticket"):
    st.session_state.history = []
    st.session_state.ticket = None
    st.rerun()

# Show the conversation so far
for turn in st.session_state.history:
    if turn["role"] == "user":
        st.chat_message("user").write(turn["text"])
    else:
        turn_ticket = json.loads(turn["text"])
        with st.chat_message("assistant"):
            st.write(turn_ticket["reply"])
            st.markdown(ticket_badges(turn_ticket))

message = st.chat_input("Describe your IT issue, or answer the bot's question")

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
    st.rerun()

# Show the latest version of the ticket
ticket = st.session_state.ticket
if ticket:
    st.divider()
    st.subheader("🎫 Your ticket")
    st.caption("This is what gets sent to the IT team. It updates as you add details.")
    with st.container(border=True):
        mood = ":orange-badge[😤 Sounds frustrated]" if ticket["frustrated"] else ""
        st.markdown(f"{ticket_badges(ticket)} :gray-badge[🌐 {ticket['language']}] {mood}")
        meaning = PRIORITY_STYLE.get(ticket["priority"].lower(), ("", "", ""))[2]
        if meaning:
            st.markdown(f"**What this priority means:** {meaning}")
        st.markdown("**Summary for the IT team**")
        st.write(ticket["summary_en"])
        with st.expander("🧠 Why the AI chose this priority"):
            st.write(ticket["reasoning"])

    if st.button("📧 Convert ticket to an HTML email"):
        with st.status("Converting ticket to an HTML email...", expanded=True) as status:
            html = ticket_to_html(ticket, on_status=st.write)
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