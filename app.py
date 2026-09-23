import json
import streamlit as st
from triage import triage, ticket_to_html

st.set_page_config(page_title="IT Helpdesk Triage", page_icon="🛠️")
st.title("🛠️ Multilingual IT Helpdesk Triage")
st.caption("📚 A learning project for practising prompt engineering. Chat in Burmese, English, Chinese, Malay, or a mix.")
st.warning("Just a learning project: no real tickets, and nobody will actually contact you. Please use made-up examples.")

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
        st.chat_message("assistant").write(json.loads(turn["text"])["reply"])

message = st.chat_input("Describe your IT issue, or answer the bot's question")

if message:
    st.session_state.history.append({"role": "user", "text": message})
    with st.spinner("Analysing..."):
        ticket = triage(st.session_state.history)
    if ticket is None:
        st.session_state.history.pop()
        st.error("Could not read the model's response. Please try again.")
        st.stop()
    st.session_state.history.append({"role": "model", "text": json.dumps(ticket, ensure_ascii=False)})
    st.session_state.ticket = ticket
    st.rerun()

# Show the latest version of the ticket
ticket = st.session_state.ticket
if ticket:
    st.divider()
    st.subheader("Current ticket")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Language", ticket["language"])
    col2.metric("Category", ticket["category"])
    col3.metric("Priority", ticket["priority"].upper())
    col4.metric("Frustrated", "Yes" if ticket["frustrated"] else "No")

    st.markdown("**How the AI reasoned before deciding priority**")
    st.write(ticket["reasoning"])
    st.markdown("**Summary for IT team**")
    st.write(ticket["summary_en"])

    if st.button("📧 Convert ticket to an HTML email"):
        with st.spinner("Converting format..."):
            html = ticket_to_html(ticket)
        if html:
            st.markdown(html, unsafe_allow_html=True)
            with st.expander("See the HTML code"):
                st.code(html, language="html")
        else:
            st.error("Conversion failed. Please try again.")