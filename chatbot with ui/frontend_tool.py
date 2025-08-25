import streamlit as st
from backend_tool import chatbot, get_chat_name, load_all_threads_with_names, save_thread_name, get_thread_name_from_history
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
import uuid

def generate_thread_id():
    return str(uuid.uuid4())

def reset_chat():
    thread_id = generate_thread_id()
    st.session_state['thread_id'] = thread_id
    add_thread(thread_id)
    st.session_state['message_history'] = []

def add_thread(thread_id, name="new chat"):
    if thread_id not in st.session_state['chat_threads']:
        st.session_state['chat_threads'][thread_id] = name or str(thread_id)

def load_conversation(thread_id):
    try:
        return chatbot.get_state(config={'configurable': {'thread_id': thread_id}}).values['messages']
    except:
        return []

def messages_to_display_format(messages):
    """Convert LangGraph messages to display format, filtering out tool messages"""
    temp_messages = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            temp_messages.append({'role': 'user', 'content': msg.content})
        elif isinstance(msg, AIMessage):
            if msg.content and msg.content.strip():
                temp_messages.append({'role': 'assistant', 'content': msg.content})
    return temp_messages
        
def initialize_chat_threads():
    if 'chat_threads_loaded' not in st.session_state:
        existing_threads = load_all_threads_with_names()
        st.session_state['chat_threads'] = existing_threads
        st.session_state['chat_threads_loaded'] = True
        
        thread_id = generate_thread_id()
        st.session_state['thread_id'] = thread_id
        add_thread(thread_id, "New Chat")
        
if 'message_history' not in st.session_state:
    st.session_state['message_history'] = []

initialize_chat_threads()

if 'thread_id' not in st.session_state:
    st.session_state['thread_id'] = generate_thread_id()
    add_thread(st.session_state['thread_id'], "New Chat")

if 'chat_threads' not in st.session_state:
    st.session_state['chat_threads'] = {}  

add_thread(st.session_state['thread_id'])

st.sidebar.title('LangGraph Chatbot')

if st.sidebar.button('Create a new conversation'):
    reset_chat()
    st.rerun()

st.sidebar.header('Chats')

for thread_id, name in list(st.session_state['chat_threads'].items())[::-1]:
    if st.sidebar.button(name, key=thread_id):
        st.session_state['thread_id'] = thread_id
        messages = load_conversation(thread_id)
        
        
        st.session_state['message_history'] = messages_to_display_format(messages)
        st.rerun()


for message in st.session_state['message_history']:
    with st.chat_message(message['role']):
        st.text(message['content'])

user_input = st.chat_input('Type here')

if user_input:
    st.session_state['message_history'].append({'role': 'user', 'content': user_input})
    with st.chat_message('user'):
        st.text(user_input)

    CONFIG = {'configurable': {'thread_id': st.session_state['thread_id']},
              "metadata": {
                  "thread_id": st.session_state["thread_id"]
              },
              "run_name": "chat_turn"}

    with st.chat_message("assistant"):
        status_holder = {"box": None, "tools": []}

        def ai_only_stream():
            for message_chunk, metadata in chatbot.stream(
                {"messages": [HumanMessage(content=user_input)]},
                config=CONFIG,
                stream_mode="messages",
            ):
                if isinstance(message_chunk, ToolMessage):
                    tool_name = getattr(message_chunk, "name", "tool")
                    status_holder["tools"].append(tool_name)

                    if status_holder["box"] is None:
                        status_holder["box"] = st.status(
                            f"🔧 Using `{tool_name}` …", expanded=True
                        )
                    else:
                        status_holder["box"].update(
                            label=f"🔧 Using `{tool_name}` …",
                            state="running",
                            expanded=True,
                        )

                if isinstance(message_chunk, AIMessage):
                    yield message_chunk.content

        ai_message = st.write_stream(ai_only_stream())

        if status_holder["box"] is not None:
            tools_used = ", ".join(set(status_holder["tools"]))
            status_holder["box"].update(
                label=f"Finished using: {tools_used}",
                state="complete",
                expanded=False,
            )

    st.session_state['message_history'].append({'role': 'assistant', 'content': ai_message})

    
    if len(st.session_state['message_history']) == 2:
        first_message = st.session_state['message_history'][0]['content']
        name = get_chat_name(first_message)
        if name and name != "New Chat":
            if save_thread_name(st.session_state['thread_id'], name):
                st.session_state['chat_threads'][st.session_state['thread_id']] = name
                st.rerun()