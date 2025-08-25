from langgraph.graph import StateGraph, START, END
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.message import add_messages
from dotenv import load_dotenv
import sqlite3
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.tools import tool
import requests

load_dotenv()

llm = ChatGoogleGenerativeAI(model = "gemini-1.5-flash")

search_tool = DuckDuckGoSearchRun(region="us-en")


@tool
def calculator(first_num: float, second_num: float, operation: str) -> dict:
    """
    Perform a basic arithmetic operation on two numbers.
    Supported operations: add, sub, mul, div
    """
    try:
        if operation == "add":
            result = first_num + second_num
        elif operation == "sub":
            result = first_num - second_num
        elif operation == "mul":
            result = first_num * second_num
        elif operation == "div":
            if second_num == 0:
                return {"error": "Division by zero is not allowed"}
            result = first_num / second_num
        else:
            return {"error": f"Unsupported operation '{operation}'"}
        
        return {"first_num": first_num, "second_num": second_num, "operation": operation, "result": result}
    except Exception as e:
        return {"error": str(e)}
    

@tool
def get_stock_price(symbol: str) -> dict:
    """
    Fetch latest stock price for a given symbol (e.g. 'AAPL', 'TSLA') 
    using Alpha Vantage with API key in the URL.
    """
    url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey=9V83D1LDAVVJ5KZQ"
    r = requests.get(url)
    return r.json()

tools = [search_tool, get_stock_price, calculator]
llm_with_tools = llm.bind_tools(tools)



class state(TypedDict):

    messages: Annotated[list[BaseMessage], add_messages]


def create_system_message():
    return SystemMessage(content="""You are a helpful AI assistant. Your knowledge cutoff is early 2024. 

CRITICAL: When users ask about events, information, or data that could have changed since early 2024, you MUST use the web search tool to get current information.

Use web search for:
- Updated news
- Current events
- Stock prices and financial data  
- Recent technology updates
- Weather information
- Any time-sensitive or frequently changing information

Use calculator for: Mathematical operations
Use stock price tool for: Getting specific stock quotes

Always prioritize current, accurate information over potentially outdated knowledge.""")

def chat_node(state: state):
    """Chat node that uses LLM with tools bound"""
    messages = state['messages']
    system_msg = create_system_message()
    
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = messages + [system_msg]
    response = llm_with_tools.invoke(messages)

    return {'messages': [response]}

tool_node = ToolNode(tools)

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
graph.add_node('tools', tool_node)

graph.add_edge(START, 'chat_node')
graph.add_conditional_edges('chat_node', tools_condition)
graph.add_edge('tools', 'chat_node')


chatbot = graph.compile(checkpointer=checkpointer)

def retrieve_all_threads():
    try:
        cursor = connection.cursor()
        cursor.execute('SELECT thread_id FROM thread_names ORDER BY created_at ASC')
        rows = cursor.fetchall()
        return [row[0] for row in rows]
    except Exception as e:
        print(f"Error retrieving threads: {e}")
        return []


def get_chat_name(msg):

    return llm.invoke(f'If the following is the first message of a conversation between a human and AI model and it is delivered by huma then give a meaningful chat name within 3 words. only tell the name.\n Message: {msg}').content

def save_thread_name(thread_id, name):
    try:
        cursor = connection.cursor()
        cursor.execute('SELECT name FROM thread_names WHERE thread_id = ?', (thread_id,))
        existing = cursor.fetchone()
        
        if not existing:
            cursor.execute('''
                INSERT INTO thread_names (thread_id, name)
                VALUES (?, ?)
            ''', (thread_id, name))
            connection.commit()
            return True
        return False
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
