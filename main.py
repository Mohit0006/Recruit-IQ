import os
import json
import sqlite3
import shutil
import requests
import chromadb
import fitz  # PyMuPDF
from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ==========================================
# 🔐 ENVIRONMENT CONFIGURATION
# ==========================================
load_dotenv() # Loads variables from .env securely

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "local").lower()
LOCAL_MODEL_NAME = os.getenv("LOCAL_MODEL_NAME", "ats-agent")
CLOUD_MODEL_NAME = os.getenv("CLOUD_MODEL_NAME", "qwen/qwen-2.5-7b-instruct")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

BHASHINI_USER_ID = os.getenv("BHASHINI_USER_ID")
BHASHINI_API_KEY = os.getenv("BHASHINI_API_KEY")
BHASHINI_PIPELINE_ID = os.getenv("BHASHINI_PIPELINE_ID")

if LLM_PROVIDER == "cloud" and not OPENROUTER_API_KEY:
    raise RuntimeError("❌ LLM_PROVIDER is set to 'cloud' but no OPENROUTER_API_KEY found in .env!")

app = FastAPI()
DB_PATH = "ats_master.db"
os.makedirs("resumes", exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 🌍 BHASHINI TRANSLATION ENGINE
# ==========================================
def translate_to_english(text_to_translate):
    """
    Detects regional language and translates resume text to English using Bhashini API.
    If API keys are missing, it safely falls back to returning the original text.
    """
    if not BHASHINI_API_KEY or not BHASHINI_PIPELINE_ID:
        return text_to_translate # Fallback if Bhashini is not configured yet
        
    try:
        print("🌍 Translating resume using Bhashini API...")
        # Bhashini Standard ULCA Pipeline REST Endpoint
        url = "https://dhruva-api.bhashini.gov.in/services/inference/pipeline"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": BHASHINI_API_KEY,
            "userID": BHASHINI_USER_ID
        }
        
        payload = {
            "pipelineTasks": [
                {"taskType": "translation", "config": {"language": {"sourceLanguage": "hi", "targetLanguage": "en"}}}
            ],
            "inputData": {"input": [{"source": text_to_translate}]}
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        translated_text = result["pipelineResponse"][0]["output"][0]["target"]
        return translated_text
        
    except Exception as e:
        print(f"⚠️ Bhashini Translation Failed (Falling back to original): {e}")
        return text_to_translate

# ==========================================
# ⚙️ BACKGROUND SYSTEM: DATABASE INGESTION
# ==========================================
def extract_text(pdf_path):
    try:
        doc = fitz.open(pdf_path)
        text = "\n".join([page.get_text() for page in doc])
        return text.strip()
    except Exception as e:
        print(f"Error reading {pdf_path}: {e}")
        return None

def process_pending_resumes():
    print("⚙️ Background Ingestion triggered. Checking for pending resumes...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS resumes_fts 
        USING fts5(candidate_name, role, text_content)
    ''')
    
    client = chromadb.PersistentClient(path="./chroma_data")
    collection = client.get_or_create_collection(name="candidate_resumes")
    
    cursor.execute("SELECT id, name, applied_role, file_path FROM candidates WHERE status = 'Pending'")
    pending_candidates = cursor.fetchall()
    
    for cand_id, name, role, file_path in pending_candidates:
        print(f"   -> Processing: {name} for {role}...")
        raw_text = extract_text(file_path)
        
        if raw_text:
            # 🚀 BHASHINI INTEGRATION TRIGGERED HERE
            final_english_text = translate_to_english(raw_text)
            
            # A. Save to Vector Database (ChromaDB)
            collection.add(
                documents=[final_english_text],
                metadatas=[{"candidate_name": name, "filename": os.path.basename(file_path), "role": role}],
                ids=[f"cand_{cand_id}"] 
            )
            
            # B. Save to Keyword Database
            cursor.execute('''
                INSERT INTO resumes_fts (candidate_name, role, text_content) 
                VALUES (?, ?, ?)
            ''', (name, role, final_english_text))
            
            cursor.execute("UPDATE candidates SET status = 'Vectorized' WHERE id = ?", (cand_id,))
            print(f"   ✅ Successfully stored {name}.")
        else:
            cursor.execute("UPDATE candidates SET status = 'Failed' WHERE id = ?", (cand_id,))
            print(f"   ❌ Failed to read {file_path}.")
            
        conn.commit()
    conn.close()

# ==========================================
# 🌐 CANDIDATE PORTAL REST ENDPOINTS
# ==========================================
@app.get("/api/jobs")
def get_active_jobs_api():
    if not os.path.exists(DB_PATH):
        return {"jobs": []}
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT UNIQUE, description TEXT)")
        cursor.execute("SELECT title, description FROM jobs")
        jobs = [{"title": row[0], "description": row[1]} for row in cursor.fetchall()]
        conn.close()
        return {"jobs": jobs}
    except Exception:
        return {"jobs": []}

@app.post("/api/apply")
async def submit_application_api(
    background_tasks: BackgroundTasks,
    full_name: str = Form(...),
    email: str = Form(...),
    role: str = Form(...),
    file: UploadFile = File(...)
):
    try:
        safe_filename = file.filename.replace(" ", "_")
        save_path = os.path.join("resumes", safe_filename)
        
        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                name TEXT, 
                email TEXT, 
                applied_role TEXT, 
                file_path TEXT, 
                status TEXT,
                assigned_interviewer_id INTEGER,
                FOREIGN KEY(assigned_interviewer_id) REFERENCES users(id)
            )
        ''')
        cursor.execute(
            "INSERT INTO candidates (name, email, applied_role, file_path, status) VALUES (?, ?, ?, ?, 'Pending')",
            (full_name, email, role, save_path)
        )
        conn.commit()
        conn.close()

        background_tasks.add_task(process_pending_resumes)
        return JSONResponse(content={"message": f"Thank you, {full_name}! Your application for {role} has been submitted."}, status_code=200)

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/trigger_ingestion")
async def trigger_ingestion(background_tasks: BackgroundTasks):
    background_tasks.add_task(process_pending_resumes)
    return {"message": "Webhook received. Ingestion started in the background."}

# ==========================================
# 🧠 FOREGROUND SYSTEM: HYBRID AI RANKING
# ==========================================
@app.post("/rank_text")
def rank_text_only(
    candidate_name: str = Form(...),
    job_description: str = Form(...),
    text_content: str = Form(...)
):
    prompt = f"""
    You are an elite, Tier-1 Technical Recruiter and Systems Architect. Evaluate the candidate strictly against the job description.
    
    Job Description:
    {job_description}
    
    Candidate Resume:
    {text_content}
    
    CRITICAL INSTRUCTION: SKILL ADJACENCY INFERENCE
    You must perform 'Skill Adjacency Inference'. Do not just look for exact keyword matches. If a candidate mentions building a specific architecture or using a specific tool, you MUST infer the foundational skills required to do so. For example: 'React' implies JavaScript/HTML/CSS. 'Docker' implies Linux/Command Line. Factor both explicit AND inferred skills into your final percentage score and recommendation tier. If a candidate lacks a keyword but possesses adjacent skills, do not penalize them heavily.

    CRITICAL MATH RULE: 
    Calculate the total FULL-TIME work experience. Ignore all "Intern", "Internship", and "Student" roles. Round the final total down to the nearest WHOLE NUMBER (e.g., 4.9 years becomes 4). 
    
    STRICT TIER RUBRIC (You MUST apply these exact rules):
    - "Fast-Track": Meets 90%+ of the core job requirements AND has strong, verifiable full-time experience.
    - "Interview": Meets 70%+ of requirements. Good foundation, but missing some "nice-to-have" skills.
    - "Borderline": Meets about 50% of requirements. Lacking required experience but shows baseline potential.
    - "Reject": Fundamentally lacks core skills, completely wrong industry, or 0 full-time experience.
    
    OUTPUT FORMAT REQUIREMENTS:
    You MUST return ONLY a raw JSON object. Do NOT wrap it in Markdown code blocks. Do NOT add any conversational text before or after the JSON.
    The JSON object must have these exact keys:
    - "email": (string, or "Not Found")
    - "phone": (string, or "Not Found")
    - "linkedin": (string, or "Not Found")
    - "experience_breakdown": (string, step-by-step math showing exactly how you calculated the total whole years)
    - "total_experience_years": (number, the final integer of FULL-TIME experience only)
    - "recommendation_tier": (string: exactly "Fast-Track", "Interview", "Borderline", or "Reject")
    - "missing_dealbreakers": (array of strings)
    - "standout_skills": (array of strings, explicit skills on resume)
    - "inferred_skills": (array of strings, hidden skills you deduced via Skill Adjacency)
    - "primary_reason": (string, explicitly reference the rubric rule and any inferred skills you used)
    """
    
    try:
        # 🚀 HYBRID ROUTING LOGIC
        if LLM_PROVIDER == "local":
            print("🧠 Evaluating via Local Ollama...")
            headers = {"Content-Type": "application/json"}
            payload = {
                "model": LOCAL_MODEL_NAME, 
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.0}
            }
            url = "http://127.0.0.1:11434/api/chat"
            
        else:
            print(f"☁️ Evaluating via Cloud ({CLOUD_MODEL_NAME})...")
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPENROUTER_API_KEY}"
            }
            payload = {
                "model": CLOUD_MODEL_NAME, 
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "response_format": {"type": "json_object"}
            }
            url = "https://openrouter.ai/api/v1/chat/completions"

        # Make the API Call
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        response_data = response.json()
        
        # Parse Response (Handles both OpenRouter and Ollama schema structures)
        if LLM_PROVIDER == "local":
            raw_content = response_data.get("message", {}).get("content")
        else:
            raw_content = response_data.get("choices", [{}])[0].get("message", {}).get("content")
        
        if not raw_content:
            raise ValueError("The AI model returned a blank response.")
            
        raw_content = raw_content.strip()
        
        # Clean markdown if present
        if raw_content.startswith("```"):
            lines = raw_content.splitlines()
            if lines[0].startswith("```"): lines = lines[1:]
            if lines and lines[-1].startswith("```"): lines = lines[:-1]
            raw_content = "\n".join(lines).strip()

        start_idx = raw_content.find("{")
        end_idx = raw_content.rfind("}")
        
        if start_idx != -1 and end_idx != -1:
            clean_json_string = raw_content[start_idx : end_idx + 1]
            parsed_json = json.loads(clean_json_string)
            return {"status": "success", "data": parsed_json}
        else:
            raise ValueError(f"No JSON brackets found. Raw output: {raw_content}")
            
    except requests.exceptions.HTTPError as e:
        raise HTTPException(status_code=500, detail="API Provider Error")
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=500, detail="The model did not return valid JSON.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
