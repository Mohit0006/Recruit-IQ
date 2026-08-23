import os
import argparse
import requests
import sys
import csv
import threading
import time
import chromadb
import sqlite3
import re
from dotenv import load_dotenv

# ==========================================
# 🔐 ENVIRONMENT CONFIGURATION
# ==========================================
load_dotenv() # Load variables from .env securely

# Dynamically route the backend URL (Defaults to localhost if not in cloud)
FASTAPI_URL = os.getenv("FASTAPI_URL", "http://127.0.0.1:8000")
DB_PATH = os.getenv("DB_PATH", "ats_master.db")

completed_count = 0
lock = threading.Lock()
all_results = []

def process_resume_text(candidate_name, text_content, jd_text, target_k):
    global completed_count
    url = f"{FASTAPI_URL}/rank_text"
    
    success = False
    for attempt in range(4): 
        try:
            data = {"candidate_name": candidate_name, "job_description": jd_text, "text_content": text_content}
            time.sleep(2)
            response = requests.post(url, data=data, timeout=300)
            
            if response.status_code == 200:
                result = response.json().get("data", {})
                result["candidate_name"] = candidate_name
                with lock:
                    all_results.append(result)
                success = True
                break 
            elif response.status_code == 429:
                time.sleep(5) 
                continue
            else:
                break 
        except Exception:
            break

    with lock:
        if success:
            completed_count += 1
        current_success = len(all_results)
        percent = (current_success / target_k) * 100
        # Prevent percentage from exceeding 100% in UI
        if percent > 100: percent = 100.0
        sys.stdout.write(f"\r⚡ Deep Evaluating: {current_success}/{target_k} successful parses ({percent:.1f}%)...")
        sys.stdout.flush()

def main():
    parser = argparse.ArgumentParser(description="Hybrid RAG Resume ATS Ranker")
    parser.add_argument("jd_path", help="Path to Job Description .txt")
    parser.add_argument("--top_k", type=int, default=10, help="Number of final resumes to evaluate")
    parser.add_argument("--role", type=str, default=None, help="Strictly filter by Job Role")
    args = parser.parse_args()

    try:
        with open(args.jd_path, "r", encoding="utf-8") as jd_file:
            jd_text = jd_file.read().strip()
    except FileNotFoundError:
        print("❌ Error: Could not find Job Description")
        sys.exit(1)

    print("\n🔍 Step 1: Executing Live Hybrid Search...")
    # Fetch a massive pool to guarantee we have enough valid candidates
    fetch_k = args.top_k * 5 
    
    # --- 1. GET SEMANTIC MATCHES (ChromaDB) ---
    print("   -> Querying Vector Engine...")
    client = chromadb.PersistentClient(path="./chroma_data")
    collection = client.get_collection(name="candidate_resumes")
    
    query_kwargs = {"query_texts": [jd_text], "n_results": fetch_k}
    if args.role:
        query_kwargs["where"] = {"role": args.role}
        
    try:
        chroma_results = collection.query(**query_kwargs)
        if not chroma_results['metadatas'] or not chroma_results['metadatas'][0]:
            print(f"\n⚠️ No candidates have applied for '{args.role}' yet.")
            sys.exit(0)
        semantic_names = [meta['candidate_name'] for meta in chroma_results['metadatas'][0]]
    except Exception:
        print(f"\n⚠️ Database Error. Are there any resumes for '{args.role}' yet?")
        sys.exit(0)

    # --- 2. GET KEYWORD MATCHES (SQLite FTS5) ---
    print("   -> Querying Keyword Engine (BM25)...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    words = re.findall(r'\b[a-zA-Z0-9]{4,}\b', jd_text.lower())
    unique_words = list(set(words))
    
    if not unique_words:
        print("\n❌ Error: No job description found. Please create the job in the system first.")
        sys.exit(1)
        
    fts_query = " OR ".join(unique_words)
    
    if args.role:
        cursor.execute('''
            SELECT candidate_name FROM resumes_fts 
            WHERE role = ? AND resumes_fts MATCH ? 
            ORDER BY rank LIMIT ?
        ''', (args.role, fts_query, fetch_k))
    else:
        cursor.execute('''
            SELECT candidate_name FROM resumes_fts 
            WHERE resumes_fts MATCH ? 
            ORDER BY rank LIMIT ?
        ''', (fts_query, fetch_k))
        
    keyword_names = [row[0] for row in cursor.fetchall()]

    # ==========================================
    # --- 3. RECIPROCAL RANK FUSION (RRF) ---
    # ==========================================
    print(f"\n🧮 Fusing Top {fetch_k} results using Reciprocal Rank Fusion (RRF)...")
    
    rrf_scores = {}
    k_constant = 60 

    for rank, name in enumerate(semantic_names, start=1):
        rrf_scores[name] = rrf_scores.get(name, 0.0) + 1.0 / (k_constant + rank)

    for rank, name in enumerate(keyword_names, start=1):
        rrf_scores[name] = rrf_scores.get(name, 0.0) + 1.0 / (k_constant + rank)

    sorted_rrf_candidates = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    
    # 👇 LOOPHOLE 1 FIX: We buffer the names so we don't run out if the AI crashes.
    buffer_limit = args.top_k * 3 
    top_names = [name for name, score in sorted_rrf_candidates[:buffer_limit]]

    placeholders = ",".join(["?"] * len(top_names))
    cursor.execute(f"SELECT candidate_name, text_content FROM resumes_fts WHERE candidate_name IN ({placeholders})", tuple(top_names))
    
    # 👇 LOOPHOLE 3 FIX: Rebuilding the exact RRF mathematical order.
    db_results = {row[0]: row[1] for row in cursor.fetchall()}
    hybrid_docs = []
    for name in top_names:
        if name in db_results:
            hybrid_docs.append((name, db_results[name]))
            
    conn.close()

    print(f"✅ RRF Math successfully locked {len(hybrid_docs)} balanced candidates. Starting evaluation...")
    
    # 👇 LOOPHOLE 2 FIX: We keep evaluating dynamically until we successfully hit your target number!
    for name, text in hybrid_docs:
        process_resume_text(name, text, jd_text, args.top_k)
        if len(all_results) >= args.top_k:
            break

    if all_results:
        print("\n\n📊 Step 3: Sorting candidates and generating final_hybrid_ranking.csv...")
        
        try:
            tier_weights = {"Fast-Track": 1, "Interview": 2, "Borderline": 3, "Reject": 4}
            
            def safe_sort(x):
                try: 
                    exp_val = str(x.get("total_experience_years", 0)).lower().replace("years", "").replace("yrs", "").strip()
                    exp = float(exp_val or 0)
                except: 
                    exp = 0.0
                return (tier_weights.get(x.get("recommendation_tier", "Unknown"), 5), -exp, x.get("candidate_name", ""))
                
            all_results.sort(key=safe_sort)

            with open("final_hybrid_ranking.csv", mode="w", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([
                    "Candidate Name", "Email", "Phone", "LinkedIn", "Est. Experience (Years)", 
                    "Math Breakdown", "Tier", "Missing Dealbreakers", "Standout Skills", 
                    "Inferred Skills", "Reasoning"
                ])
                for r in all_results:
                    dealbreakers = r.get("missing_dealbreakers", [])
                    if isinstance(dealbreakers, str): dealbreakers = [dealbreakers]
                    
                    standout = r.get("standout_skills", [])
                    if isinstance(standout, str): standout = [standout]
                    
                    inferred = r.get("inferred_skills", [])
                    if isinstance(inferred, str): inferred = [inferred]

                    try: 
                        exp_str = str(r.get("total_experience_years", 0)).lower().replace("years", "").replace("yrs", "").strip()
                        exp_int = int(round(float(exp_str or 0)))
                    except: 
                        exp_int = 0
                    
                    writer.writerow([
                        r.get("candidate_name", "Unknown"), r.get("email", "Not Found"),
                        r.get("phone", "Not Found"), r.get("linkedin", "Not Found"), exp_int,
                        r.get("experience_breakdown", "None"), r.get("recommendation_tier", "Unknown"), 
                        ", ".join(dealbreakers) if dealbreakers else "None", 
                        ", ".join(standout) if standout else "None", 
                        ", ".join(inferred) if inferred else "None", 
                        r.get("primary_reason", "No reason provided")
                    ])
            print(f"🎉 Done! Results saved to final_hybrid_ranking.csv.")
            
        except PermissionError:
            print("\n❌ FILE ERROR: CSV is open. Close it and run again!")
        except Exception as e:
            print(f"\n❌ CRITICAL CRASH DURING SAVING: {e}")
            
if __name__ == "__main__":
    main()
