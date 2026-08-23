import streamlit as st
import pandas as pd
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import subprocess
import base64
import sys
import sqlite3
import datetime
import json
import time
import re
from streamlit_cookies_controller import CookieController
from dotenv import load_dotenv

# ==========================================
# 🔐 ENVIRONMENT CONFIGURATION
# ==========================================
load_dotenv() # Securely loads all credentials from .env

# Hybrid LLM Config
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "local").lower()
LOCAL_MODEL_NAME = os.getenv("LOCAL_MODEL_NAME", "ats-agent")
CLOUD_MODEL_NAME = os.getenv("CLOUD_MODEL_NAME", "qwen/qwen-2.5-7b-instruct")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Zoom Config
ZOOM_ACCOUNT_ID = os.getenv("ZOOM_ACCOUNT_ID")
ZOOM_CLIENT_ID = os.getenv("ZOOM_CLIENT_ID")
ZOOM_CLIENT_SECRET = os.getenv("ZOOM_CLIENT_SECRET")
ZOOM_HOST_EMAIL = os.getenv("ZOOM_HOST_EMAIL")

# SMTP Config
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")

DB_PATH = "ats_master.db"

# ==========================================
# PAGE CONFIGURATION & THEME
# ==========================================
st.set_page_config(page_title="ATS Enterprise Command", page_icon="🤖", layout="wide", initial_sidebar_state="expanded")

def inject_gemini_theme():
    st.markdown("""
    <style>
    .stApp { background-color: #131314; }
    ::-webkit-scrollbar { width: 8px; background-color: transparent; }
    ::-webkit-scrollbar-thumb { background-color: #444746; border-radius: 10px; }
    ::-webkit-scrollbar-thumb:hover { background-color: #5f6368; }
    ::-webkit-scrollbar-track { background-color: transparent; }
    div[data-testid="stChatInput"] { padding-bottom: 0.5rem !important; }
    div[data-testid="stChatInput"] textarea {
        background-color: #1e1f20 !important; border: 1px solid #444746 !important;
        border-radius: 24px !important; color: #e3e3e3 !important; padding: 12px 20px !important;
    }
    [data-testid="stChatMessage"] { background-color: transparent !important; border: none !important; padding: 1rem 0; }
    div[data-testid="stChatMessageContent"] {
        background-color: #1e1f20 !important; padding: 12px 20px !important; border-radius: 12px !important; display: inline-block;
    }
    [data-testid="stSidebar"] { background-color: #171717; border-right: 1px solid #333; }
    [data-testid="stHeader"] { background-color: transparent; }
    #MainMenu, footer, [data-testid="stHeader"] .stAppDeployButton { display: none; visibility: hidden; }
    div.stButton > button:first-child {
        background-color: transparent; border: 1px solid #565869; color: #ECECEC;
        border-radius: 20px; padding: 10px 24px; transition: all 0.2s ease;
    }
    div.stButton > button:first-child:hover { background-color: #40414f; border-color: #ECECEC; }
    </style>
    """, unsafe_allow_html=True)

inject_gemini_theme()

# ==========================================
# DEDICATED PDF VIEWER ROUTING
# ==========================================
if "view_resume" in st.query_params:
    target_email = st.query_params["view_resume"]
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT file_path FROM candidates WHERE email = ?", (target_email,))
    result = cursor.fetchone()
    conn.close()
    
    if result and result[0] and os.path.exists(result[0]):
        with open(result[0], "rb") as f:
            base64_pdf = base64.b64encode(f.read()).decode('utf-8')
        
        st.markdown("""
            <style>
            header {visibility: hidden;}
            .block-container {padding: 0rem 0rem; max-width: 100%;}
            </style>
        """, unsafe_allow_html=True)
        
        pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="1000px" type="application/pdf" style="border: none; height: 100vh;"></iframe>'
        st.markdown(pdf_display, unsafe_allow_html=True)
    else:
        st.error("⚠️ Document not found or has been removed from the server.")
    
    st.stop()


# ==========================================
# AUTOMATED OUTREACH ENGINE
# ==========================================
def generate_zoom_link(topic, start_date, start_time):
    try:
        token_url = f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={ZOOM_ACCOUNT_ID}"
        client_creds = f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}"
        encoded_creds = base64.b64encode(client_creds.encode()).decode()
        headers = {"Authorization": f"Basic {encoded_creds}", "Content-Type": "application/x-www-form-urlencoded"}
        token_res = requests.post(token_url, headers=headers, timeout=10)
        token_res.raise_for_status()
        access_token = token_res.json().get("access_token")
        
        meeting_url = f"https://api.zoom.us/v2/users/{ZOOM_HOST_EMAIL}/meetings"
        meeting_headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        meeting_data = {
            "topic": f"Interview: {topic}", "type": 2, "start_time": f"{start_date}T{start_time}:00",
            "duration": 45, "timezone": "Asia/Kolkata",
            "settings": {"host_video": True, "participant_video": True, "join_before_host": False, "mute_upon_entry": True}
        }
        meeting_res = requests.post(meeting_url, headers=meeting_headers, json=meeting_data, timeout=10)
        meeting_res.raise_for_status()
        return meeting_res.json().get("join_url"), None
    except Exception as e: return None, f"Zoom API Error: {str(e)}"

def send_interview_email(smtp_server, candidate_name, candidate_email, role_name, interview_date, interview_time, zoom_url, interviewer_name=None):
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = candidate_email
        msg['Subject'] = f"Interview Invitation: {role_name} at Our Company"
        
        display_name = interviewer_name if interviewer_name else "one of our team members"
        
        body = f"""Hello {candidate_name},\n\nCongratulations! You have been shortlisted for the {role_name} position. We were highly impressed by your profile and would like to invite you to an interview with {display_name}.\n\n🗓️ Scheduled Date: {interview_date}\n⏰ Scheduled Time: {interview_time} (IST)\n👤 Interviewer: {display_name}\n🎥 Zoom Meeting Link: {zoom_url}\n\nPlease join the link a few minutes before the scheduled time. Let us know if this schedule works for you.\n\nBest regards,\nTalent Acquisition Team"""
        
        msg.attach(MIMEText(body, 'plain'))
        smtp_server.send_message(msg)
        return True, ""
    except Exception as e: return False, str(e)

# ==========================================
# ENTERPRISE SQL DATABASE FUNCTIONS
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, role TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT UNIQUE, description TEXT)")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            name TEXT, 
            email TEXT, 
            applied_role TEXT, 
            file_path TEXT, 
            status TEXT, 
            assigned_interviewer_id INTEGER,
            zoom_link TEXT,
            FOREIGN KEY(assigned_interviewer_id) REFERENCES users(id)
        )
    """)
    
    try:
        cursor.execute("ALTER TABLE candidates ADD COLUMN interview_date TEXT")
        cursor.execute("ALTER TABLE candidates ADD COLUMN interview_time TEXT")
    except sqlite3.OperationalError: 
        pass 
        
    default_users = [
        ('admin', 'admin123', 'Admin'),
        ('mohit', 'mohit123', 'Interviewer'),
        ('sarah', 'sarah123', 'Interviewer'),  
        ('david', 'david123', 'Interviewer')   
    ]
    
    for u, p, r in default_users:
        cursor.execute("SELECT id FROM users WHERE username = ?", (u,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (u, p, r))
            
    conn.commit()
    conn.close()

init_db()

def authenticate_user(username, password):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE username = ? AND password = ?", (username, password))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def load_jobs():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT title, description FROM jobs")
        jobs = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()
        return jobs
    except Exception: return {}

def save_job(title, description):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO jobs (title, description) VALUES (?, ?)", (title, description))
    conn.commit()
    conn.close()

def delete_job(title):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs WHERE title = ?", (title,))
    conn.commit()
    conn.close()

def get_db_summary():
    if not os.path.exists(DB_PATH): return "Database is empty."
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM candidates")
        total_cands = cursor.fetchone()[0]
        cursor.execute("SELECT applied_role, COUNT(*) FROM candidates GROUP BY applied_role")
        role_counts_db = dict(cursor.fetchall())
        jobs = load_jobs()
        
        summary = f"Total Candidates in System: {total_cands}.\nActive Job Postings ({len(jobs)}): {', '.join(jobs.keys())}.\nCandidates by Role: "
        role_details = [f"{role_counts_db.get(job, 0)} applied for '{job}'" for job in jobs.keys()]
        for role, count in role_counts_db.items():
            if role not in jobs: role_details.append(f"{count} applied for closed role '{role}'")
        summary += ", ".join(role_details) + "."
        conn.close()
        return summary
    except Exception as e: return f"Database error: {e}"

def run_ranking_action(target_role, top_k, jd_text):
    with open("ui_uploaded_jd.txt", "w", encoding="utf-8") as f: f.write(jd_text)
    custom_env = os.environ.copy()
    custom_env["PYTHONIOENCODING"] = "utf-8"
    cmd = [sys.executable, "rag_ranker.py", "ui_uploaded_jd.txt", "--top_k", str(top_k), "--role", target_role]
    process = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=custom_env)
    return process.returncode == 0, process.stderr

# ==========================================
# AI AGENT INTENT PARSER (HYBRID ROUTING)
# ==========================================
def chat_with_agent(user_text, chat_history):
    db_state = get_db_summary()
    
    system_prompt = f"""
    You are the ATS Enterprise Agent backend. You must communicate exclusively by selecting a tool and returning its exact JSON structure. Do not return markdown blocks, code blocks, or raw text.
    
    CURRENT SYSTEM STATE:
    {db_state}
    
    CRITICAL WORKFLOW PROTOCOL:
    1. STRICT DATA COLLECTION: You MUST collect Title, Description, Location, and Salary from the user. If the user only provides a title, you MUST use the "chat" tool to ask for the remaining Description, Location, and Salary. 
    2. NO HALLUCINATION: DO NOT invent, guess, or use placeholders (like "TBD" or "Remote") to fill the tool JSON. 
    3. DRAFT & CONFIRM: Once ALL 4 pieces of data are provided by the user, draft the job and ask for confirmation.
    4. FINALIZE (CREATE): Use the 'create_job' tool ONLY after the user explicitly confirms.
    5. EMAIL OUTREACH: If the user asks to send an email or invite a candidate, execute the 'send_invites' action IMMEDIATELY. Do NOT ask for confirmation.
    6. STRICT GRID DISPLAY RULE: For general questions like "What jobs are open?", you MUST use the "chat" tool. DO NOT use the "show_grid" tool unless the user EXPLICITLY asks to see the candidates.
    7. UNSCHEDULE: If the user asks to cancel, clear, or unschedule interviews for a specific person, use the 'unschedule_interviews' action.
    
    TOOLS:
    - {{"action": "create_job", "title": "...", "description": "...", "location": "...", "salary": "..."}}
    - {{"action": "delete_job", "title": "..."}}
    - {{"action": "execute_ranking", "target_role": "...", "top_k": int}} 
    - {{"action": "send_invites", "target_role": "...", "num_candidates": int, "assign_to": "..."}}
    - {{"action": "rank_and_invite", "target_role": "...", "top_k": int, "num_to_invite": int, "assign_to": "..."}} 
    - {{"action": "unschedule_interviews", "interviewer": "..."}}
    - {{"action": "show_grid", "response": "..."}} 
    - {{"action": "chat", "response": "..."}} 
    """
    
    api_messages = [{"role": "system", "content": system_prompt}]
    for msg in chat_history[-6:]:
        api_messages.append({"role": msg["role"], "content": msg["content"]})
    api_messages.append({"role": "user", "content": user_text})
    
    try:
        # 🚀 HYBRID ROUTING LOGIC
        if LLM_PROVIDER == "local":
            headers = {"Content-Type": "application/json"}
            payload = {
                "model": LOCAL_MODEL_NAME, 
                "messages": api_messages, 
                "stream": False, 
                "format": "json",
                "options": {"temperature": 0.0}
            }
            url = "http://127.0.0.1:11434/api/chat"
        else:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPENROUTER_API_KEY}"
            }
            payload = {
                "model": CLOUD_MODEL_NAME, 
                "messages": api_messages, 
                "temperature": 0.0,
                "response_format": {"type": "json_object"}
            }
            url = "https://openrouter.ai/api/v1/chat/completions"

        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        response_data = response.json()
        
        # Parse based on provider
        if LLM_PROVIDER == "local":
            message_content = response_data.get('message', {}).get('content')
        else:
            message_content = response_data.get("choices", [{}])[0].get("message", {}).get("content")
        
        raw_text = message_content.strip() if message_content else ""
        
        if not raw_text or len(raw_text) == 0:
            return {
                "action": "chat", 
                "response": "⚠️ The AI model returned a blank response. Please try your command again.", 
                "suggested_prompts": ["What jobs are open right now?"]
            }
        
        clean_text = raw_text.lower().replace("_", "").replace("-", "").strip()
        if "rankandinvite" in clean_text and "{" not in raw_text:
            parsed_json = {"action": "rank_and_invite", "top_k": 3, "num_to_invite": 1}
        elif "executeranking" in clean_text and "{" not in raw_text:
            parsed_json = {"action": "execute_ranking", "top_k": 10}
        elif "sendinvites" in clean_text and "{" not in raw_text:
            parsed_json = {"action": "send_invites", "num_candidates": 1}
        else:
            match = re.search(r'\{.*?\}', raw_text, re.DOTALL)
            parsed_json = json.loads(match.group(0)) if match else {"action": "chat", "response": raw_text, "suggested_prompts": ["What jobs are open?"]}
            
        action = parsed_json.get("action")
        
        # BACKEND OVERRIDE LOOPHOLE FIX
        user_text_lower = user_text.lower()
        if "unschedule" in user_text_lower or "cancel" in user_text_lower:
            if "mohit" in user_text_lower:
                parsed_json = {"action": "unschedule_interviews", "interviewer": "mohit"}
                action = "unschedule_interviews"
            elif "sarah" in user_text_lower:
                parsed_json = {"action": "unschedule_interviews", "interviewer": "sarah"}
                action = "unschedule_interviews"
            elif "david" in user_text_lower:
                parsed_json = {"action": "unschedule_interviews", "interviewer": "david"}
                action = "unschedule_interviews"
        
        if action == "create_job":
            desc = parsed_json.get("description", "")
            loc = parsed_json.get("location", "")
            sal = parsed_json.get("salary", "")
            
            if len(desc) < 20 or not loc or not sal or loc.lower() in ["tbd", "unknown", ""] or sal.lower() in ["tbd", "unknown", ""]:
                return {
                    "action": "chat", 
                    "response": "⚠️ **System Security Alert:** Cannot open a job without a full description, location, and salary. Please provide the exact missing details so I can draft the posting.", 
                    "suggested_prompts": ["Cancel job creation."]
                }
        
        elif action in ["execute_ranking", "rank_and_invite", "send_invites"]:
            target_role = parsed_json.get("target_role", "")
            top_k = parsed_json.get("top_k") or parsed_json.get("num_candidates") or 3
            num_to_invite = parsed_json.get("num_to_invite", 1)
            
            if "assign_to" not in parsed_json:
                user_text_lower = user_text.lower()
                if "sarah" in user_text_lower: parsed_json["assign_to"] = "Sarah"
                elif "david" in user_text_lower: parsed_json["assign_to"] = "David"
                elif "mohit" in user_text_lower: parsed_json["assign_to"] = "Mohit"
            
            active_jobs = load_jobs()
            if not target_role:
                for job_title in active_jobs.keys():
                    if job_title.lower() in user_text.lower():
                        target_role = job_title
                        parsed_json["target_role"] = target_role
                        break
            
            if not target_role and len(active_jobs) == 1:
                target_role = list(active_jobs.keys())[0]
                
            if not target_role:
                return {"action": "chat", "response": "Please specify which role you want to process.", "suggested_prompts": ["What jobs are open?"]}
            elif f"0 applied for '{target_role}'" in db_state or target_role not in db_state:
                return {"action": "chat", "response": f"SYSTEM ALERT: 0 candidates found in the database for '{target_role}'.", "suggested_prompts": ["What jobs are open?"]}
            
            parsed_json["target_role"] = target_role
            if action == "rank_and_invite":
                parsed_json["top_k"] = int(top_k)
                parsed_json["num_to_invite"] = int(num_to_invite)
            else:
                parsed_json["top_k"] = int(top_k)
        
        return parsed_json
    except Exception as e: 
        return {"action": "chat", "response": f"System Error: ({e})", "suggested_prompts": []}

# ==========================================
# SESSION & GATEKEEPER INIT
# ==========================================
controller = CookieController()
saved_user = controller.get('auth_username')
saved_role = controller.get('auth_role')

if saved_user and saved_role:
    st.session_state.logged_in = True
    st.session_state.username = saved_user
    st.session_state.role = saved_role
elif "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.role = None

if "chat_messages" not in st.session_state: st.session_state.chat_messages = []
if "agent_suggestions" not in st.session_state: st.session_state.agent_suggestions = ["What jobs are open right now?", "Show me the database summary"]

# ==========================================
# AUTHENTICATION UI
# ==========================================
def login_screen():
    st.markdown("""<div style="text-align: center; padding-top: 10vh; padding-bottom: 30px;"><h1 style="color: white; font-weight: 600;">ATS Command Center</h1><p style="color: #ECECEC;">Please log in to continue</p></div>""", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Secure Login", use_container_width=True):
                role = authenticate_user(username, password)
                if role:
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.session_state.role = role
                    controller.set('auth_username', username)
                    controller.set('auth_role', role)
                    st.rerun() 
                else: st.error("❌ Invalid username or password.")

# ==========================================
# MAIN APPLICATION ROUTING
# ==========================================
if not st.session_state.logged_in:
    login_screen()

else:
    # --- COMMON SIDEBAR (ALL ROLES) ---
    selected_name = None
    selected_interviewer_id = None
    
    with st.sidebar:
        initial = st.session_state.username[0].upper()
        st.markdown(f"""
            <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 25px; padding: 10px; background-color: #1e1f20; border-radius: 12px; border: 1px solid #444746;">
                <div style="background-color: #3b82f6; width: 45px; height: 45px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 20px; color: white;">{initial}</div>
                <div style="line-height: 1.2;">
                    <div style="font-size: 1.1rem; font-weight: 600; color: #e3e3e3;">{st.session_state.username.title()}</div>
                    <div style="font-size: 0.85rem; color: #a1a1aa; text-transform: uppercase;">{st.session_state.role}</div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        if st.button("Log Out", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.username = None
            st.session_state.role = None
            st.session_state.chat_messages = [] 
            controller.remove('auth_username')
            controller.remove('auth_role')
            st.rerun()
            
        # --- ADMIN ONLY SIDEBAR SETTINGS ---
        if st.session_state.role == "Admin":
            st.divider()
            st.header("⚙️ Agent Settings")
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("SELECT id, username FROM users WHERE role='Interviewer'")
                interviewers = cursor.fetchall()
                conn.close()
                if interviewers:
                    interviewer_options = {name.title(): uid for uid, name in interviewers}
                    selected_name = st.selectbox("Assign Interviewer (Fallback)", list(interviewer_options.keys()))
                    selected_interviewer_id = interviewer_options[selected_name]
                else: st.warning("⚠️ No interviewers found.")
            except Exception: pass
            
            agent_role = st.text_input("Interviewer Title", value="Lead Systems Architect")
            agent_date = st.date_input("Default Interview Date", datetime.date.today() + datetime.timedelta(days=2))
            agent_time = st.time_input("Default Interview Time", datetime.time(14, 0))
            st.divider()
            with st.expander("Database Status"): st.code(get_db_summary())


    # ==========================================
    # INTERVIEWER EXCLUSIVE UI 
    # ==========================================
    if st.session_state.role == "Interviewer":
        st.markdown("<h2 style='color: #e3e3e3; padding-top: 2rem;'>📅 My Interview Schedule</h2>", unsafe_allow_html=True)
        st.markdown("View your assigned candidates, join Zoom rooms, and check their resumes.")
        
        try:
            conn = sqlite3.connect(DB_PATH)
            query = f"""
                SELECT c.name as 'Candidate Name', c.interview_date as 'Date', c.interview_time as 'Time', 
                       c.email as 'Email', c.applied_role as 'Role', c.zoom_link as 'Meeting Link'
                FROM candidates c 
                JOIN users u ON c.assigned_interviewer_id = u.id 
                WHERE u.username = '{st.session_state.username}'
            """
            df_my_interviews = pd.read_sql_query(query, conn)
            conn.close()
            
            if df_my_interviews.empty: 
                st.info("You currently have no upcoming interviews scheduled.")
            else: 
                st.markdown("### 👥 Assigned Candidates")
                
                df_my_interviews['Resume'] = df_my_interviews['Email'].apply(
                    lambda email: f"/?view_resume={email}"
                )
                
                display_df = df_my_interviews[['Candidate Name', 'Date', 'Time', 'Email', 'Role', 'Meeting Link', 'Resume']]
                
                st.dataframe(
                    display_df, 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "Meeting Link": st.column_config.LinkColumn("Meeting Link", display_text="Join Zoom Room 🎥"),
                        "Resume": st.column_config.LinkColumn("Resume", display_text="View 📄")
                    }
                )
                
        except Exception as e: 
            st.error(f"Error loading schedule: {e}")

    # ==========================================
    # ADMIN EXCLUSIVE UI (CHATBOT & EXECUTION)
    # ==========================================
    elif st.session_state.role == "Admin":
        chat_container = st.container(height=550, border=False)

        with chat_container:
            if not st.session_state.chat_messages:
                st.markdown("<h2 style='text-align: center; color: #e3e3e3; margin-top: 10vh;'>Hello, how can I help you today?</h2>", unsafe_allow_html=True)
                if st.session_state.agent_suggestions:
                    col1, col2, col3, col4 = st.columns([1, 2, 2, 1])
                    with col2:
                        if st.button(st.session_state.agent_suggestions[0], key="h1", use_container_width=True):
                            st.session_state.chat_messages.append({"role": "user", "content": st.session_state.agent_suggestions[0]})
                            st.session_state.agent_suggestions = []
                            st.rerun()
                    with col3:
                        if len(st.session_state.agent_suggestions) > 1:
                            if st.button(st.session_state.agent_suggestions[1], key="h2", use_container_width=True):
                                st.session_state.chat_messages.append({"role": "user", "content": st.session_state.agent_suggestions[1]})
                                st.session_state.agent_suggestions = []
                                st.rerun()
            else:
                for msg in st.session_state.chat_messages:
                    with st.chat_message(msg["role"]):
                        st.write(msg["content"])
                        if msg.get("show_grid") and os.path.exists("final_hybrid_ranking.csv"):
                            try:
                                df = pd.read_csv("final_hybrid_ranking.csv").drop_duplicates(subset=["Email"])
                                if "Candidate Name" in df.columns: df["Candidate Name"] = df["Candidate Name"].apply(lambda x: str(x).replace("_", " ").title())
                                df = df.reset_index(drop=True)
                                df.index += 1
                                df.insert(0, 'Rank', df.index)
                                
                                # Use the dynamic actual count for rendering
                                actual_count = len(df)
                                display_limit = min(actual_count, msg.get("top_k", 25))
                                st.dataframe(df.head(display_limit), use_container_width=True, hide_index=True)
                            except Exception: pass

                if st.session_state.agent_suggestions:
                    st.write("💡 **Suggested Actions:**")
                    cols = st.columns(len(st.session_state.agent_suggestions))
                    for idx, suggestion in enumerate(st.session_state.agent_suggestions):
                        with cols[idx]:
                            if st.button(suggestion, key=f"sug_{idx}", use_container_width=True):
                                st.session_state.chat_messages.append({"role": "user", "content": suggestion})
                                st.session_state.agent_suggestions = [] 
                                st.rerun()

        if user_input := st.chat_input("Command the AI..."):
            st.session_state.chat_messages.append({"role": "user", "content": user_input})
            st.session_state.agent_suggestions = [] 
            st.rerun()

        # --- EXECUTION ENGINE ---
        if st.session_state.chat_messages and st.session_state.chat_messages[-1]["role"] == "user":
            user_msg = st.session_state.chat_messages[-1]["content"]
            
            with chat_container:
                with st.chat_message("assistant"):
                    with st.spinner("Processing..."):
                        intent = chat_with_agent(user_msg, st.session_state.chat_messages[:-1])
                        action = intent.get("action", "chat")
                        st.session_state.agent_suggestions = intent.get("suggested_prompts", [])
                        
                        if action == "create_job":
                            t, d = intent.get("title"), intent.get("description")
                            save_job(t, d)
                            resp = f"✅ Successfully opened: **{t}**."
                            st.write(resp); st.session_state.chat_messages.append({"role": "assistant", "content": resp})
                        
                        elif action == "delete_job":
                            t = intent.get("title")
                            delete_job(t)
                            resp = f"🗑️ Successfully closed and removed the job posting for **{t}**."
                            st.write(resp); st.session_state.chat_messages.append({"role": "assistant", "content": resp})
                        
                        elif action == "execute_ranking":
                            role_to_run = intent.get("target_role")
                            k_to_run = intent.get("top_k", 10)
                            success, err = run_ranking_action(role_to_run, k_to_run, load_jobs().get(role_to_run, ""))
                            
                            if success:
                                if os.path.exists("final_hybrid_ranking.csv"):
                                    df = pd.read_csv("final_hybrid_ranking.csv")
                                    df = df.reset_index(drop=True)
                                    df.index += 1
                                    if 'Rank' not in df.columns:
                                        df.insert(0, 'Rank', df.index)
                                    
                                    actual_count = len(df)
                                    display_count = min(actual_count, k_to_run)
                                    
                                    if actual_count < k_to_run:
                                        resp = f"✅ Ranking complete. Note: Only {actual_count} candidates successfully parsed. Displaying them below:"
                                    else:
                                        resp = f"✅ Ranking complete. Displaying top {display_count} candidates below:"
                                        
                                    st.write(resp)
                                    st.dataframe(df.head(display_count), hide_index=True)
                                    st.session_state.chat_messages.append({"role": "assistant", "content": resp, "show_grid": True, "top_k": display_count})
                                else:
                                    resp = "✅ Ranking complete, but no candidates were found."
                                    st.write(resp)
                                    st.session_state.chat_messages.append({"role": "assistant", "content": resp})
                            else:
                                st.write(f"❌ Ranking failed: {err}")
                                st.session_state.chat_messages.append({"role": "assistant", "content": f"❌ Ranking failed: {err}"})
                        
                        elif action == "rank_and_invite" or action == "send_invites":
                            target_role = intent.get("target_role", intent.get("role", intent.get("job_title", "Open Role")))
                            
                            if action == "rank_and_invite":
                                top_k = intent.get("top_k", 3)
                                num_to_invite = intent.get("num_to_invite", 1)
                                success, err = run_ranking_action(target_role, top_k, load_jobs().get(target_role, ""))
                                if not success:
                                    err_msg = f"❌ Error: Ranking failed: {err}"
                                    st.write(err_msg); st.session_state.chat_messages.append({"role": "assistant", "content": err_msg})
                                    st.stop()
                            else:
                                num_to_invite = intent.get("num_candidates", 1)
                                    
                            if not os.path.exists("final_hybrid_ranking.csv"):
                                err_msg = "❌ Error: No CSV generated or Ranking data missing."
                                st.write(err_msg); st.session_state.chat_messages.append({"role": "assistant", "content": err_msg})
                            else:
                                df = pd.read_csv("final_hybrid_ranking.csv")
                                df = df.reset_index(drop=True)
                                df.index += 1
                                if 'Rank' not in df.columns:
                                    df.insert(0, 'Rank', df.index)
                                
                                if action == "rank_and_invite":
                                    actual_count = len(df)
                                    display_count = min(actual_count, top_k)
                                    
                                    if actual_count < top_k:
                                        grid_msg = f"✅ Ranking complete. Note: Only {actual_count} candidates successfully parsed. Displaying them below:"
                                    else:
                                        grid_msg = f"✅ Ranking complete. Displaying top {display_count} candidates below:"
                                        
                                    st.write(grid_msg)
                                    st.dataframe(df.head(display_count), hide_index=True)
                                    st.session_state.chat_messages.append({"role": "assistant", "content": grid_msg, "show_grid": True, "top_k": display_count})
                                
                                dynamic_assign = intent.get("assign_to")
                                active_interviewer_id = selected_interviewer_id
                                active_interviewer_name = selected_name
                                
                                if dynamic_assign:
                                    try:
                                        db_conn = sqlite3.connect(DB_PATH)
                                        cursor = db_conn.cursor()
                                        cursor.execute("SELECT id, username FROM users WHERE LOWER(username)=? AND role='Interviewer'", (dynamic_assign.lower(),))
                                        matched_user = cursor.fetchone()
                                        db_conn.close()
                                        if matched_user:
                                            active_interviewer_id = matched_user[0]
                                            active_interviewer_name = matched_user[1].title()
                                    except Exception: pass
                                
                                invited_count = 0
                                mail_server = None
                                log_messages = []
                                try:
                                    mail_server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10)
                                    mail_server.starttls()
                                    mail_server.login(SENDER_EMAIL, SENDER_PASSWORD)
                                    
                                    for index, row in df.head(num_to_invite).iterrows():
                                        exact_db_name = str(row.get("Candidate Name", "Candidate"))
                                        cand_name_clean = exact_db_name.replace("_", " ").title()
                                        
                                        # Strict lookup to grab portal-submitted email address
                                        true_email = row.get("Email", SENDER_EMAIL)
                                        try:
                                            db_conn = sqlite3.connect(DB_PATH)
                                            cursor = db_conn.cursor()
                                            cursor.execute("SELECT email FROM candidates WHERE name = ? AND applied_role = ?", (exact_db_name, target_role))
                                            db_result = cursor.fetchone()
                                            if db_result and db_result[0]:
                                                true_email = db_result[0]
                                            db_conn.close()
                                        except Exception: pass
                                        
                                        zoom_url, zoom_err = generate_zoom_link(topic=f"{cand_name_clean} - {target_role}", start_date=str(agent_date), start_time=str(agent_time))
                                        if zoom_err: zoom_url = "https://zoom.us/j/fallback"
                                        
                                        success_email, err_email = send_interview_email(
                                            mail_server, cand_name_clean, true_email, target_role, agent_date, agent_time, zoom_url, interviewer_name=active_interviewer_name
                                        )
                                        
                                        if success_email:
                                            invited_count += 1
                                            assign_tag = f" (Assigned to: {active_interviewer_name})" if active_interviewer_id and active_interviewer_name else ""
                                            log_messages.append(f"✅ **Sent:** Interview details sent to {cand_name_clean}{assign_tag}")
                                            
                                            if active_interviewer_id:
                                                try:
                                                    db_conn = sqlite3.connect(DB_PATH)
                                                    # Strict condition matching parameters to prevent multiple row assignment leaks
                                                    db_conn.execute(
                                                        "UPDATE candidates SET status = 'Interview Scheduled', assigned_interviewer_id = ?, zoom_link = ?, interview_date = ?, interview_time = ? WHERE name = ? AND applied_role = ?", 
                                                        (active_interviewer_id, zoom_url, str(agent_date), str(agent_time), exact_db_name, target_role) 
                                                    )
                                                    db_conn.commit()
                                                    db_conn.close()
                                                except Exception: pass
                                        else:
                                            log_messages.append(f"❌ **Failed:** Could not email {cand_name_clean}.")
                                            
                                except Exception as e: log_messages.append(f"❌ **SMTP Error:** Check credentials.")
                                finally:
                                    if mail_server:
                                        try: mail_server.quit()
                                        except: pass
                                
                                final_text = f"🎉 **Outreach Complete:** Emailed {invited_count} candidate(s) for {target_role}.\n\n" + "\n".join(log_messages)
                                st.write(final_text)
                                st.session_state.chat_messages.append({"role": "assistant", "content": final_text})

                        elif action == "unschedule_interviews":
                            target_interviewer = intent.get("interviewer", "").lower()
                            if not target_interviewer:
                                resp = "⚠️ Please specify which interviewer's schedule you want to clear."
                                st.write(resp)
                                st.session_state.chat_messages.append({"role": "assistant", "content": resp})
                            else:
                                try:
                                    db_conn = sqlite3.connect(DB_PATH)
                                    cursor = db_conn.cursor()
                                    cursor.execute("SELECT id, username FROM users WHERE LOWER(username)=? AND role='Interviewer'", (target_interviewer,))
                                    matched_user = cursor.fetchone()
                                    
                                    if matched_user:
                                        interviewer_id = matched_user[0]
                                        interviewer_name = matched_user[1].title()
                                        
                                        cursor.execute("SELECT COUNT(*) FROM candidates WHERE assigned_interviewer_id = ?", (interviewer_id,))
                                        count = cursor.fetchone()[0]
                                        
                                        if count > 0:
                                            cursor.execute('''
                                                UPDATE candidates 
                                                SET status = 'Vectorized', 
                                                    assigned_interviewer_id = NULL, 
                                                    zoom_link = NULL, 
                                                    interview_date = NULL, 
                                                    interview_time = NULL 
                                                WHERE assigned_interviewer_id = ?
                                            ''', (interviewer_id,))
                                            db_conn.commit()
                                            resp = f"✅ Successfully unscheduled {count} interview(s) assigned to **{interviewer_name}**. The candidates have been returned to the general pool."
                                        else:
                                            resp = f"ℹ️ **{interviewer_name}** has no interviews scheduled at the moment."
                                    else:
                                        resp = f"❌ Could not find an interviewer named '{target_interviewer}' in the system."
                                    
                                    db_conn.close()
                                    st.write(resp)
                                    st.session_state.chat_messages.append({"role": "assistant", "content": resp})
                                except Exception as e:
                                    resp = f"❌ Database Error while unscheduling: {e}"
                                    st.write(resp)
                                    st.session_state.chat_messages.append({"role": "assistant", "content": resp})

                        elif action == "show_grid":
                            response_text = intent.get("response", "Here are the candidates:")
                            st.write(response_text)
                            if os.path.exists("final_hybrid_ranking.csv"):
                                df = pd.read_csv("final_hybrid_ranking.csv")
                                # Clean data rendering directly from the source tracking table safely
                                df = df.reset_index(drop=True)
                                df.index += 1
                                df.insert(0, 'Rank', df.index)
                                st.dataframe(df.head(50), hide_index=True)
                            st.session_state.chat_messages.append({"role": "assistant", "content": response_text, "show_grid": True, "top_k": 50})
                        
                        else:
                            response_text = intent.get("response")
                            if not response_text or len(str(response_text).strip()) == 0:
                                response_text = "I am ready to help. What would you like to do?"
                            st.write(response_text)
                            st.session_state.chat_messages.append({"role": "assistant", "content": response_text})
