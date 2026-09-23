import streamlit as st
from triage import triage

st.set_page_config(page_title="IT Helpdesk Triage", page_icon="🛠️")
st.title("🛠️ Multilingual IT Helpdesk Triage")
st.caption("Write your IT problem in Burmese, English, Chinese, Malay, or a mix")

message = st.text_area("Describe your IT issue")

if st.button("Submit ticket") and message.strip():
    with st.spinner("Analysing your message..."):
        ticket = triage(message)

    if ticket is None:
        st.error("Could not read the model's response. Please try again.")
        st.stop()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Language", ticket["language"])
    col2.metric("Category", ticket["category"])
    col3.metric("Priority", ticket["priority"].upper())
    col4.metric("Frustrated", "Yes" if ticket["frustrated"] else "No")

    st.subheader("Summary for IT team")
    st.write(ticket["summary_en"])

    st.subheader("Reply to user")
    st.info(ticket["reply"])