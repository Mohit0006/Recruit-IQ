import sqlite3
import os

def create_database():
    db_path = "ats_master.db"
    
    # Connect to SQLite (this automatically creates the file if it doesn't exist)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Table 1: Store the active Job Postings
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT UNIQUE NOT NULL,
            description TEXT NOT NULL
        )
    ''')
    
    # Table 2: Store Candidate Applications and their processing status
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            applied_role TEXT NOT NULL,
            file_path TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'Pending' -- Can be: Pending, Vectorized, Failed
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"✅ Enterprise Database created successfully at {db_path}")

if __name__ == "__main__":
    create_database()
