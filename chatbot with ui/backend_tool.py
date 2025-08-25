from langgraph.graph import StateGraph, START, END
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.message import add_messages
from dotenv import load_dotenv
import sqlite3
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.tools import tool
import requests
import urllib.parse

load_dotenv()

llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash")

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
    try:
        url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey=9V83D1LDAVVJ5KZQ"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        
        if "Error Message" in data:
            return {"error": f"API Error: {data['Error Message']}"}
        if "Note" in data:
            return {"error": f"API Limit: {data['Note']}"}
        if "Global Quote" not in data:
            return {"error": "Invalid response format from Alpha Vantage"}
            
        quote = data["Global Quote"]
        return {
            "symbol": quote.get("01. symbol", symbol),
            "price": quote.get("05. price", "N/A"),
            "change": quote.get("09. change", "N/A"),
            "change_percent": quote.get("10. change percent", "N/A")
        }
    except requests.exceptions.RequestException as e:
        return {"error": f"Network error: {str(e)}"}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}

@tool
def search_wikipedia(query: str) -> str:
    """
    Search Wikipedia for a given query and return a short summary.
    Example: search_wikipedia("Albert Einstein")
    """
    try:
        
        clean_query = query.strip().replace(' ', '_')
        encoded_query = urllib.parse.quote(clean_query, safe='')
        
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_query}"
        headers = {'User-Agent': 'LangGraph-Chatbot/1.0'}
        
        r = requests.get(url, headers=headers, timeout=10)
        
        if r.status_code == 200:
            data = r.json()
            extract = data.get("extract", "No summary found.")
            title = data.get("title", query)
            return f"Wikipedia Summary for '{title}':\n{extract}"
        elif r.status_code == 404:
            return f"No Wikipedia page found for '{query}'. Try a different search term."
        else:
            return f"Error {r.status_code}: Could not fetch data from Wikipedia."
            
    except requests.exceptions.RequestException as e:
        return f"Network error accessing Wikipedia: {str(e)}"
    except Exception as e:
        return f"Error searching Wikipedia: {str(e)}"

@tool
def solve_with_wolfram(query: str) -> str:
    """
    Solve math/physics/chemistry problems using Wolfram Alpha.
    Example: solve_with_wolfram("integrate x^2 from 0 to 1")
    """
    try:
        APP_ID = "A7WL3GG78U"  
        encoded_query = urllib.parse.quote(query)
        url = f"http://api.wolframalpha.com/v1/result?appid={APP_ID}&i={encoded_query}"
        
        r = requests.get(url, timeout=15)
        
        if r.status_code == 200:
            return f"Wolfram Alpha Result: {r.text}"
        elif r.status_code == 501:
            return "Wolfram Alpha couldn't interpret your query. Please try rephrasing."
        else:
            return f"Error {r.status_code}: Could not get result from Wolfram Alpha."
            
    except requests.exceptions.RequestException as e:
        return f"Network error accessing Wolfram Alpha: {str(e)}"
    except Exception as e:
        return f"Error using Wolfram Alpha: {str(e)}"

@tool
def run_code(language: str, code: str) -> str:
    """
    Run code using Piston API (supports python, javascript, c, cpp, java, etc.)
    Example: run_code("python", "print(2+2)")
    """
    try:
        url = "https://emkc.org/api/v2/piston/execute"
        
        
        language_mapping = {
            "python3": "python",
            "js": "javascript",
            "node": "javascript",
            "c++": "cpp"
        }
        
        api_language = language_mapping.get(language.lower(), language.lower())
        
        payload = {
            "language": api_language,
            "version": "*",  
            "files": [{"content": code}]
        }
        
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        
        result = r.json()
        
        if "run" in result:
            output = result["run"].get("output", "No output")
            stderr = result["run"].get("stderr", "")
            
            if stderr:
                return f"Output: {output}\nErrors: {stderr}"
            return f"Output: {output}"
        else:
            return f"Error: {result.get('message', 'Unknown error occurred')}"
            
    except requests.exceptions.RequestException as e:
        return f"Network error: {str(e)}"
    except Exception as e:
        return f"Error running code: {str(e)}"

@tool
def get_weather(city: str, country_code: str = "") -> dict:
    """
    Get current weather for a city. 
    Example: get_weather("Dhaka", "BD") or get_weather("London")
    """
    try:
        if country_code:
            geocoding_url = f"http://api.openweathermap.org/geo/1.0/direct?q={city},{country_code}&limit=1&appid=demo"
        else:
            geocoding_url = f"http://api.openweathermap.org/geo/1.0/direct?q={city}&limit=1&appid=demo"
        
        city_coords = {
            "dhaka": {"lat": 23.8103, "lon": 90.4125},
            "london": {"lat": 51.5074, "lon": -0.1278},
            "new york": {"lat": 40.7128, "lon": -74.0060},
            "tokyo": {"lat": 35.6762, "lon": 139.6503},
            "paris": {"lat": 48.8566, "lon": 2.3522}
        }
        
        city_lower = city.lower()
        if city_lower in city_coords:
            lat = city_coords[city_lower]["lat"]
            lon = city_coords[city_lower]["lon"]
        else:
            lat, lon = 23.8103, 90.4125 
        
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&hourly=temperature_2m,relativehumidity_2m,windspeed_10m"
        
        r = requests.get(weather_url, timeout=10)
        r.raise_for_status()
        
        data = r.json()
        current = data["current_weather"]
        
        weather_descriptions = {
            0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
            45: "Fog", 48: "Depositing rime fog", 51: "Light drizzle", 53: "Moderate drizzle",
            55: "Dense drizzle", 61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain"
        }
        
        weather_desc = weather_descriptions.get(current["weathercode"], "Unknown")
        
        return {
            "city": city,
            "temperature": f"{current['temperature']}°C",
            "windspeed": f"{current['windspeed']} km/h",
            "condition": weather_desc,
            "weather_code": current["weathercode"]
        }
        
    except requests.exceptions.RequestException as e:
        return {"error": f"Network error: {str(e)}"}
    except KeyError as e:
        return {"error": f"Missing data in weather response: {str(e)}"}
    except Exception as e:
        return {"error": f"Error getting weather: {str(e)}"}

tools = [search_tool, get_stock_price, calculator, search_wikipedia, solve_with_wolfram, run_code, get_weather]
llm_with_tools = llm.bind_tools(tools)

class state(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

def create_system_message():
    return SystemMessage(content="""You are a helpful AI assistant with access to several tools. Your knowledge cutoff is early 2024.

IMPORTANT: When users ask about current events, recent information, or anything that could have changed since early 2024, use the web search tool first.

Available tools:
1. **DuckDuckGoSearchRun**: For current events, news, sports results, recent information
2. **calculator**: For mathematical operations (add, sub, mul, div)  
3. **get_stock_price**: For current stock prices
4. **search_wikipedia**: For encyclopedic information and summaries
5. **solve_with_wolfram**: For complex math, physics, chemistry problems
6. **run_code**: For executing code in various languages (python, javascript, c, cpp, java)
7. **get_weather**: For current weather information (use city name)

Use web search for:
- Sports results from 2024 onwards 
- Current events, breaking news
- Recent technology updates, product releases  
- Any time-sensitive information

Examples:
- "Who won La Liga 2024-25?" → Use DuckDuckGoSearchRun
- "What's 25 * 4?" → Use calculator
- "Weather in London" → Use get_weather("London")
- "Integrate x^2" → Use solve_with_wolfram
- "Run this Python code: print('hello')" → Use run_code

Always prioritize accuracy and use the most appropriate tool for each query.""")

def chat_node(state: state):
    """Chat node that uses LLM with tools bound"""
    messages = state['messages']
    
    if not messages or not isinstance(messages[0], SystemMessage):
        system_msg = create_system_message()
        messages = [system_msg] + messages
    
    response = llm_with_tools.invoke(messages)
    return {'messages': [response]}

tool_node = ToolNode(tools)

connection = sqlite3.connect(database='chatbot.db', check_same_thread=False)
checkpointer = SqliteSaver(conn=connection)

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
    return llm.invoke(f'If the following is the first message of a conversation between a human and AI model and it is delivered by human then give a meaningful chat name within 3 words. only tell the name.\n Message: {msg}').content

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

