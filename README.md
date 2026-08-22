




https://github.com/user-attachments/assets/aa91e39e-0cdc-4432-8955-b5c3ee7ca3f7





# RecruitIQ — AI-Powered Recruitment Automation Platform

> A production-grade, multi-component Applicant Tracking System that automates the entire hiring process using a hybrid RAG engine, LLM evaluation, FastAPI microservices, and third-party API integrations — built solo from scratch.


## 🧠 What is RecruitIQ?

RecruitIQ is a dual-interface recruitment platform that eliminates manual resume screening and hiring logistics entirely. Candidates apply through a public portal. Admins type plain-English commands. The AI handles everything else — ranking, scheduling, and outreach — autonomously.

The system is built around a **hybrid RAG engine** that combines semantic vector search (ChromaDB) and keyword search (SQLite FTS5), fused via **Reciprocal Rank Fusion (RRF)**, and evaluated by an **open-source LLM** via the OpenRouter API.

```
## ⚙️ System Architecture

========================================================================================
                      RECRUITIQ: TRUE END-TO-END SYSTEM WORKFLOW
========================================================================================

[ 🧑‍💻 CANDIDATE ]                             [ 👔 RECRUITER / ADMIN ]
       │                                                │
       ▼                                                ▼
 ┌──────────────────────┐                     ┌──────────────────────┐
 │ Candidate Portal     │                     │ Command Center       │
 │     (React)          │                     │ (Streamlit UI)       │
 └──────┬───────────────┘                     └──────┬───────────────┘
        │ 1. Submits Resume                          │ 9. NLP Command
        ▼                                            ▼
 ┌──────────────────────┐                     ┌──────────────────────┐
 │ Input Validation     │                     │ AI Intent Engine     │
 │ (Regex + Compulsory) │                     │ (OpenRouter API)     │
 └──────┬───────────────┘                     └──────┬───────────────┘
        │ 2. Data Cleared                            │ 10. JSON Intent Return
        ▼                                            ▼
 ┌───────────────────────────────────────────────────────────────────┐
 │                       CENTRAL SQLITE DATABASE                     │
 │          (Jobs Table | Users Table | Candidates Table)            │
 └──────┬────────────────────────────────────────────┬───────────────┘
        │ 3. Logs "Pending"                          │ 11. Fetches Target JD
        ▼                                            │
 ┌──────────────────────┐                            │
 │ File Storage         │                            │
 │ (Local /resumes PDF) │                            │
 └──────┬───────────────┘                            │
        │ 4. Async Webhook                           │
        ▼                                            │
 ┌──────────────────────────────────────┐            │
 │ FASTAPI BACKGROUND: /trigger_ingestion            │
 │                                      │            │
 │  ┌────────────────┐                  │            │
 │  │ 5. PyMuPDF Read├───┐              │            │
 │  │ (Full Text)    │   │              │            │
 │  └────────────────┘   │              │            │
 │                       ▼              │            │
 │ ┌─────────────┐  ┌─────────────┐     │            │
 │ │ 6. ChromaDB │  │ 7. SQL FTS5 │     │            │
 │ │ (Vectors)   │  │ (Keywords)  │     │            │
 │ └──────┬──────┘  └──────┬──────┘     │            │
 │        │                │            │            │
 │        └───────┬────────┘            │            │
 │                │ 8. Mark 'Vectorized'│            │
 └────────────────┼─────────────────────┘            │
                  │                                  │
                  ▼                                  ▼
           ┌─────────────────────────────────────────┴───────────────────────────────────┐
           │                     THE RAG ENGINE (rag_ranker.py)                          │
           │                                                                             │
           │  ┌────────────────┐                  ┌──────────────────────────┐           │
           │  │ 12. Semantic   ├───┐          ┌──►│ 14. Reciprocal Rank      │           │
           │  │ Search (Chroma)│   │          │   │     Fusion (RRF Math)    │           │
           │  └────────────────┘   │          │   └──────────┬───────────────┘           │
           │                       ├───►(FUSE)┘              │                           │
           │  ┌────────────────┐   │                         ▼                           │
           │  │ 13. Keyword    ├───┘              ┌──────────────────────────┐           │
           │  │ Search (FTS5)  │                  │ 15. POST Full Resumes to │           │
           │  └────────────────┘                  │     FastAPI (/rank_text) │           │
           │                                      └──────────┬───────────────┘           │
           │  ┌────────────────┐                             │                           │
           │  │ 18. Output CSV │◄── 17. Return JSON ─────────┘                           │
           │  │ (final ranking)│    Evaluations                                          │
           │  └────────────────┘                                                         │
           └──────────┬──────────────────────────────────────────────────────────────────┘
                      │      ▲ 
                      │      │ 16. FastAPI Prompts Local llm (Open-Source LLM)
                      │      ▼ 
                      │ [ Local llm Evaluator ]
                      │
                      ▼
               ┌──────────────────────┐
               │ Data Orchestration   │
               │ (Pandas DataFrame)   │
               └──────┬───────────────┘
                      │ 19. Cleans Index & Renders Grid in UI
                      ▼
 ┌──────────────────────┐                     ┌──────────────────────┐
 │ ZOOM OAUTH2 API      │◄────────────────────┤ Automation Engine    │
 │ (Generates Meeting)  │  20. Provisions     │ (Zoom + SMTP Logics) │
 └──────────────────────┘                     └──────┬───────────────┘
                                                     │ 21. Dispatches Invite
                                                     ▼
                                              [ 📧 CANDIDATE INBOX ]


```
## 🚀 Key Features

### 🔍 Hybrid RAG Engine
Combines **ChromaDB vector semantic search** with **SQLite FTS5 keyword search**, fused via the **Reciprocal Rank Fusion (RRF)** algorithm. This dual-retrieval approach delivers significantly more accurate rankings than single-method retrieval — capturing both conceptual similarity and exact keyword matches simultaneously.

### 🤖 LLM Evaluator
After RRF fusion, full resume texts are POSTed to a FastAPI `/rank_text` endpoint, which prompts an **open-source LLM via OpenRouter API** to evaluate and score each candidate based on years of experience, tech stack alignment, and project relevance. Returns structured JSON evaluations.

### ⚡ FastAPI Async Microservice
A dedicated background service with two endpoints:
- `/trigger_ingestion` — triggered via async webhook on resume submission; runs PyMuPDF extraction, ChromaDB vectorization, and FTS5 indexing without blocking the main dashboard
- `/rank_text` — accepts resume text and JD context, prompts the LLM evaluator, returns scored JSON

### 💬 NLP Chat Agent
Admins type plain-English commands like *"Rank top 3 candidates for Senior Full Stack Engineer and assign to Sarah."* The OpenRouter API parses intent into a structured JSON object, extracts role, limit, and assignee, and executes the action autonomously on the live database.

### 📅 Zoom OAuth2 Integration
Dynamically provisions secure, scheduled video interview rooms per candidate with custom configurations — mute on entry, video enabled — via the Zoom OAuth2 REST API.

### 📧 SMTP Outreach Automation
Automatically dispatches personalized multi-part MIME interview invitation emails containing the candidate's scheduled time, Zoom meeting link, and assigned interviewer name.

### 🔐 Role-Based Access Control (RBAC)
Two strictly separated interfaces:
- **Candidate Portal** — public-facing with Regex email validation, mandatory field checks, and automatic file sanitization
- **Admin Command Center** — secure internal dashboard with full AI chat agent and database execution access; Interviewers get read-only access

### 📄 Custom PDF Rendering Engine
Engineered a URL routing bypass (`/?view_resume=email`) that decodes raw binary PDF files into Base64 streams and renders them in a full-screen iframe — solving the browser `file://` security restriction without any external dependencies.

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI, Streamlit |
| AI / RAG | ChromaDB, SQLite FTS5, Reciprocal Rank Fusion |
| LLM | Open-Source LLM via OpenRouter API |
| PDF Processing | PyMuPDF |
| Database | SQLite (Jobs, Users, Candidates) |
| Data Orchestration | Pandas |
| Automation | Zoom OAuth2 REST API, smtplib (SMTP) |
| Security | RBAC, Base64 PDF Streaming, Regex Validation |

---

## 📊 How the RAG Process Works (Step by Step)

1. **Resume submitted** via Candidate Portal → stored in `/resumes`, logged as `Pending` in SQLite
2. **Async webhook** fires to FastAPI `/trigger_ingestion`
3. **PyMuPDF** extracts full text from the PDF
4. Text is **simultaneously indexed** — embedded into ChromaDB (vectors) and indexed in SQLite FTS5 (keywords). Candidate marked `Vectorized`.
5. **Admin types NLP command** → OpenRouter API parses intent → fetches target Job Description from SQLite
6. RAG engine runs **ChromaDB semantic search** + **FTS5 keyword search** in parallel
7. Both result sets are **fused via Reciprocal Rank Fusion (RRF)** — a mathematically proven re-ranking algorithm
8. Top candidates' full resumes are **POSTed to FastAPI `/rank_text`**
9. FastAPI **prompts an open-source LLM** to score each candidate with structured JSON evaluations
10. Results compiled into `final_hybrid_ranking.csv` → **Pandas cleans, deduplicates, and resets index**
11. Clean ranking grid rendered in UI → **Zoom meetings provisioned + invitation emails dispatched**

---

## 📩 Full Source Code

> Full source code available on request — reach out via [LinkedIn](https://www.linkedin.com/in/mohit-balwani-050715413)

---

## 👤 Author

Built independently by [Mohit Balwani](https://www.linkedin.com/in/mohit-balwani-050715413)

[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-blue?style=for-the-badge&logo=linkedin)](https://www.linkedin.com/in/mohit-balwani-050715413)
