from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import leetcode
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import openai

openai.organization = "org-Y9xGpSD0R2P9uEbCvJamEpRB"
openai.api_key = "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"
openai.Model.list()

class LoginData(BaseModel):
    session_cookie: str
    csrf_token: str

class LogoutData(BaseModel):
    user_name: str

class PromptData(BaseModel):
    user_name: str
    topic: str

# Set up the WebDriver
uri = "mongodb+srv://admin:ronaldo7@cluster0.1wvi2gh.mongodb.net/?retryWrites=true&w=majority"
# Create a new client and connect to the server
client = MongoClient(uri, server_api=ServerApi('1'))
# Send a ping to confirm a successful connection
try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)

app = FastAPI()

# CORS configuration
origins = [
    "http://localhost:63342"  # Add your allowed origins here
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_user_data(api_response):
    user_name = api_response.user_name
    num_solved = api_response.num_solved
    num_total = api_response.num_total
    solved_set = []
    for pair in api_response.stat_status_pairs:
        if pair.status:
            solved_set.append(pair.stat.question_id)

    user_map = {"user_name": user_name,
                "num_solved": num_solved,
                "num_total": num_total,
                "solved": solved_set}
    return user_map

def create_prompt(user_name, topic):
    cursor = client['Cluster0']['users'].find_one({"user_name": user_name})
    solved_problems = client['Cluster0']['problems'].find({
        "id": {"$in": cursor["solved"]},
        "topic": {"$elemMatch": {"$eq": topic}}
    }).limit(10)
    unsolved_problems = client['Cluster0']['problems'].find({
        "id": {"$in": cursor["solved"]},"topic": {"$elemMatch": {"$eq": topic}}
    }).limit(10)
    prompt = "Here are the " + topic + " problems solved by a particular user on the leetcode platform: \n"
    for sp in solved_problems:
        prompt += str(sp["id"]) + ". " + sp["title"] + "\n"
    prompt += "\nThese are a list of unsolved " + topic + " problems:"
    for usp in unsolved_problems:
        prompt += str(usp["id"]) + ". " + usp["title"] + "\n"
    return prompt

def openai_call(prompt):
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "user", "content": prompt},
        ]
    )
    return response['choices'][0]['message']['content']

@app.post("/login/")
async def login(loginData: LoginData):
    print(loginData)
    configuration = leetcode.Configuration()
    configuration.api_key["x-csrftoken"] = loginData.csrf_token
    configuration.api_key["csrftoken"] = loginData.csrf_token
    configuration.api_key["LEETCODE_SESSION"] = loginData.session_cookie
    configuration.api_key["Referer"] = "https://leetcode.com"
    configuration.debug = False

    api_instance = leetcode.DefaultApi(leetcode.ApiClient(configuration))
    api_response = api_instance.api_problems_topic_get(topic="all")
    print(api_response)
    user_data = get_user_data(api_response)
    client['Cluster0']['users'].insert_one(user_data)
    return [user_data['user_name'], user_data['num_solved'], user_data['num_total']]


@app.post("/report/")
async def report(promptData: PromptData):
    prompt = create_prompt(promptData.user_name, promptData.topic)
    prompt += "Provide a detailed report on where the user stands and rate them out of 5. Explain in 4 paragraphs."
    temp = openai_call(prompt)
    temp = "<br />".join(temp.split("\n"))
    return temp

@app.post("/recommendations/")
async def recommendations(promptData: PromptData):
    prompt = create_prompt(promptData.user_name, promptData.topic)
    prompt += "" \
              "Please reorder the unsolved questions above for the best learning curve" \
              "Retain the question numbers from my list" \
              "Provide only the list of questions with their question numbers in the output."
    temp = openai_call(prompt)
    temp = "<br />".join(temp.split("\n"))
    return temp

@app.post("/logout/")
async def logout(logoutData: LogoutData):
    client['Cluster0']['users'].delete_one({"user_name": logoutData.user_name})
    return True

