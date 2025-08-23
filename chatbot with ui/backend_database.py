from langgraph.graph import StateGraph, START, END
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.message import add_messages
from dotenv import load_dotenv
import sqlite3

load_dotenv()

llm = ChatGoogleGenerativeAI(model = "gemini-1.5-flash")

class state(TypedDict):

    messages: Annotated[list[BaseMessage], add_messages]

def chat_node(state: state):

    messages = state['messages']
    response = llm.invoke(messages)

    return {'messages': [response]}

connection = sqlite3.connect(database='chatbot.db', check_same_thread=False)
checkpointer = SqliteSaver(conn = connection)

def init_thread_names_table():
    cursor = connection.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS thread_names(
                   thread_id TEXT PRIMARY KEY,
                   name TEXT NOT NULL,
                   created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    connection.commit()

init_thread_names_table()

graph = StateGraph(state)

graph.add_node('chat_node', chat_node)

graph.add_edge(START, 'chat_node')
graph.add_edge('chat_node', END)

chatbot = graph.compile(checkpointer=checkpointer)

def retrieve_all_threads():
    all_threads = set()
    for checkpoint in checkpointer.list(None):
        all_threads.add(checkpoint.config['configurable']['thread_id'])

    return list(all_threads)

def get_chat_name(msg):

    return llm.invoke(f'If the following is the first message of a conversation between a human and AI model and it is delivered by huma then give a meaningful chat name within 3 words. only tell the name.\n Message: {msg}').content

def save_thread_name(thread_id, name):
    
    try:
        cursor = connection.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO thread_names (thread_id, name)
            VALUES (?, ?)
        ''', (thread_id, name))
        connection.commit()
        return True
    except Exception as e:
        print(f"Error saving thread name: {e}")
        return False

def get_thread_name_from_db(thread_id):
    
    try:
        cursor = connection.cursor()
        cursor.execute('SELECT name FROM thread_names WHERE thread_id = ?', (thread_id,))
        result = cursor.fetchone()
        return result[0] if result else None
    except Exception as e:
        print(f"Error getting thread name: {e}")
        return None

def get_thread_name_from_history(thread_id):
    
    saved_name = get_thread_name_from_db(thread_id)
    if saved_name:
        return saved_name
    
    
    try:
        state = chatbot.get_state(config={'configurable': {'thread_id': thread_id}})
        if state and state.values and 'messages' in state.values:
            messages = state.values['messages']
            
            for msg in messages:
                if isinstance(msg, HumanMessage):
                    name = get_chat_name(msg.content)
                    
                    save_thread_name(thread_id, name)
                    return name
        return "New Chat"
    except:
        return "New Chat"

def load_all_threads_with_names():
    
    threads = retrieve_all_threads()
    thread_names = {}
    
    for thread_id in threads:
        
        saved_name = get_thread_name_from_db(thread_id)
        if saved_name:
            thread_names[thread_id] = saved_name
        else:

            name = get_thread_name_from_history(thread_id)
            thread_names[thread_id] = name
    
    return thread_names

def delete_thread_name(thread_id):
    
    try:
        cursor = connection.cursor()
        cursor.execute('DELETE FROM thread_names WHERE thread_id = ?', (thread_id,))
        connection.commit()
        return True
    except Exception as e:
        print(f"Error deleting thread name: {e}")
        return False

def get_all_saved_thread_names():
    
    try:
        cursor = connection.cursor()
        cursor.execute('SELECT thread_id, name FROM thread_names ORDER BY created_at DESC')
        return dict(cursor.fetchall())
    except Exception as e:
        print(f"Error getting all thread names: {e}")
        return {}
