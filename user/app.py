from dotenv import load_dotenv
from fastapi import FastAPI , HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import mysql.connector
from mysql.connector import Error
import os
import redis
import pickle
from langchain_core.prompts import PromptTemplate, ChatPromptTemplate
from langchain_groq import ChatGroq
from langchain.chains import LLMChain
from langchain.schema import HumanMessage, AIMessage
from langchain.memory import ConversationBufferMemory
import webbrowser
# from flow import flow_generator
from typing import Dict
# from mentor_ai import mentor_ai_res

load_dotenv()
app = FastAPI()


# UI MIDDLEWARES-------------------------------------------------------

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Enable CORS to allow requimport pickleests from other origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods, including POST
    allow_headers=["*"],  # Allows all headers
)




# Database connection configuration-------------------------------------
DB_CONFIG = {
    'host': 'localhost',
    'user': 'fahim',
    'password': '12112',
    'database': 'AI_Mentor'
}

def get_db_connection():
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

#USERID and NAME EXTRACTOR-----------------------------------------------------
user_id = ""
user_name = ""
def get_user_id_by_username(username: str) -> str:
    connection = None
    try:
        connection = get_db_connection()  # Assume this function exists to create a DB connection
        if not connection:
            raise Exception("Database connection error")

        cursor = connection.cursor(dictionary=True)
        
        query = "SELECT user_id FROM user_table WHERE user_name = %s"
        cursor.execute(query, (username,))
        
        result = cursor.fetchone()
        
        if result:
            return result['user_id']
        else:
            return None

    except Error as e:
        print(f"Error: {e}")
        return None
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()
            
            
def get_username_by_email(email: str) -> str:
    connection = None
    try:
        connection = get_db_connection()
        if not connection:
            raise Exception("Database connection error")

        cursor = connection.cursor(dictionary=True)
        
        query = "SELECT user_name FROM user_table WHERE mail_id = %s"
        cursor.execute(query, (email,))
        
        result = cursor.fetchone()
        
        if result:
            return result['user_name']
        else:
            return None

    except Error as e:
        print(f"Error: {e}")
        return None
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()





# Pydantic models----------------------------------------------------------
class UserSignUp(BaseModel):
    name: str
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str
    
class ChatInput(BaseModel):
    user_id: str
    message: str

class MentorInput(BaseModel):
    message: str
    

flowchart_storage: Dict[str, str] = {}
class FlowchartRequest(BaseModel):
    topic: str
    
#Data extractor-----------------------------------------------------
redis_client = redis.Redis(host='localhost', port=6379, db=0)

class ChatInput(BaseModel):
    user_id: str
    message: str

groq_api_key = "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"

def get_conversation_memory(user_id: str):
    """Retrieve the conversation memory for a specific user from Redis."""
    memory_data = redis_client.get(user_id)
    if memory_data is None:
        memory = ConversationBufferMemory(memory_key="history", return_messages=True)
    else:
        memory = pickle.loads(memory_data)
    return memory

def save_conversation_memory(user_id: str, memory):
    """Save the updated conversation memory for a user in Redis."""
    redis_client.set(user_id, pickle.dumps(memory))
    
def extract_user_convo(user_id):
    
        def conversation_to_string(memory):
            conversation = ""
            for message in memory.chat_memory.messages:
                if isinstance(message, HumanMessage):
                    conversation += f"Human: {message.content}\n"
                elif isinstance(message, AIMessage):
                    conversation += f"AI: {message.content}\n"
            return conversation.strip()
        r = redis.Redis(host='localhost', port=6379, db=0)

        serialized_data = r.get(user_id)

        if serialized_data:
            data = pickle.loads(serialized_data)
            # print(type(data))
            str_data = conversation_to_string(data)
            print(str_data)
        else:
            print("No data found for 'user1'")
            
        return str_data
    

#TOOLCALL---------------------------------------------------

def process_tool_call(response: str):
    if "<tool_call>" in response and "</tool_call>" in response:
        tool_call_start = response.index("<tool_call>")
        tool_call_end = response.index("</tool_call>") + len("</tool_call>")
        tool_call_string = response[tool_call_start:tool_call_end]
        
        # Extract JSON from tool call
        json_str = tool_call_string.replace("<tool_call>", "").replace("</tool_call>", "").strip()
        try:
            tool_call = json.loads(json_str)
            if tool_call.get("name") == "generateResponse":
                user_message = tool_call.get("arguments", {}).get("userMessage")
                if user_message:
                    # Here, instead of generating a new response, we'll return the user message
                    # as it's already the AI's response to the user
                    return user_message
        except json.JSONDecodeError:
            print("Invalid JSON in tool call")
    
    # If no valid tool call is found, return the original response
    return response


#-----------------------------------------------------
    
# ENDPOINTS --------------------------------------------------------------------

@app.post("/signup")
async def signup(user: UserSignUp):
    global user_id
    global user_name
    connection = get_db_connection()
    if not connection:
        raise HTTPException(status_code=500, detail="Database connection error")

    try:
        cursor = connection.cursor()

        # Check if the username already exists
        cursor.execute("SELECT * FROM user_table WHERE user_name = %s", (user.name,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Username already exists")

        # Check if the email already exists
        cursor.execute("SELECT * FROM user_table WHERE mail_id = %s", (user.email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Email already exists")

        # Insert the new user
        insert_query = "INSERT INTO user_table (user_name, mail_id, password_) VALUES (%s, %s, %s)"
        cursor.execute(insert_query, (user.name, user.email, user.password))
        connection.commit()
        
        user_id = get_user_id_by_username(user.name)
        user_name = user.name
        
        print("\n\n\n\n",user_id,user_name)

        return {"message": "User registered successfully"}

    except mysql.connector.Error as e:
        connection.rollback()
        raise HTTPException(status_code=400, detail=f"Error during registration: {str(e)}")
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()
            
            
@app.post("/login")
async def login(user: UserLogin):
    global user_id
    global user_name
    connection = get_db_connection()
    if not connection:
        raise HTTPException(status_code=500, detail="Database connection error")

    try:
        cursor = connection.cursor(dictionary=True)

        select_query = "SELECT * FROM user_table WHERE mail_id = %s"
        cursor.execute(select_query, (user.email,))
        user_data = cursor.fetchone()

        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")

        if user_data['password_'] != user.password:
            raise HTTPException(status_code=401, detail="Incorrect password")
        
        user_name = get_username_by_email(user.email)
        user_id = get_user_id_by_username(user_name)
        
        user_name = user_name
        
        print("\n\n\n\n",user_id,user_name)



        return {"message": "Login successful"}

    except mysql.connector.Error as e:
        raise HTTPException(status_code=400, detail=f"Error during login: {str(e)}")
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()
            
            
@app.post("/chat")
async def chat(chat_input: ChatInput):
    # user_id = chat_input.user_id
    user_message = chat_input.message
    status = False
    
    
    memory = get_conversation_memory(user_id)

    llm = ChatGroq(groq_api_key=groq_api_key, model_name="llama-3.1-70b-versatile")

    prompt_template = """you are a helpfull assistant to assist user in booking guest room.
        here is the data of house owner : 
        Sno	house_owner_name	number_of_room_available	max days	min days location
        1	rahul	5	30	1 27 East Coast Road, Chennai 600041
        2	john	4	15	2 15 Anna Nagar Main Road, Madurai 625020
        3	david	1	30	1 8 Bharathiar Salai, Coimbatore 641001
        4	mukesh	2	15	1 42 Rockfort Road, Tiruchirappalli 620001
        5	riya	2	20	1 19 Beach Road, Kanyakumari 629702
        6	rio	4	15	1 53 Gandhi Road, Salem 636007
        7	gokul	5	30	1 11 VOC Street, Thoothukudi 628001
        8	sivam	2	25	1 36 Jawaharlal Nehru Road, Vellore 632001
        9	lokesh	1	30	1 19 Beach Road, Kanyakumari 629702
        10	naveen	2	15	1 7 Anna Salai, Tirunelveli 627001
        
        








22 Kamarajar Salai, Thanjavur 613001

        
        there are columns : 1.houseownername 2.no_of_roomavailable 3.max_days they can stay 4.min_days they need to stay
        
        note:
        1. based on the house owner data you can answer the user queary
        2. once user complete there booking of room then say exactely "thank you check your mail"
        3. give response in structured if you give houseowner details make it as list

        Here is the conversation history:
        {history}

    Now, the user has asked the following question:
    {human_input}
    """

    prompt = PromptTemplate(template=prompt_template, input_variables=["history", "human_input"])

    chain = LLMChain(llm=llm, prompt=prompt, memory=memory)
    response = chain.predict(human_input=user_message)
    
    processed_response = process_tool_call(response)


    save_conversation_memory(user_id, memory)
    # print(response)
    history_string = extract_user_convo(user_id)
    print(history_string)
    if "thank you check your mail" in processed_response.lower():
        print("\n\n\n---------------------------------------------------",type(history_string))
        response1 = bio_summarizer(history_string)
    return {"response": processed_response}



@app.post("/profile")
async def chat():
    global user_name
    print(user_name)
    return {
    "name": user_name,
    "role": "Web Developer | AI Enthusiast",
    "progress": 85,
    "courses": 12,
    "rating": 4.8
    }
    

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
