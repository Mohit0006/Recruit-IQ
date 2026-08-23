import sqlite3

try:
    conn = sqlite3.connect("ats_master.db")
    cursor = conn.cursor()
    
    print("\n--- 📊 DATABASE HEALTH X-RAY ---")
    
    # 1. Check statuses
    cursor.execute("SELECT status, COUNT(*) FROM candidates GROUP BY status")
    statuses = cursor.fetchall()
    print("\nCURRENT PIPELINE STATUS:")
    for status, count in statuses:
        print(f" -> {count} candidates are currently: {status}")
        
    # 2. Check roles
    cursor.execute("SELECT applied_role, COUNT(*) FROM candidates GROUP BY applied_role")
    roles = cursor.fetchall()
    print("\nCANDIDATES BY ROLE:")
    for role, count in roles:
        print(f" -> {count} candidates applied for: '{role}'")
        
    conn.close()
except Exception as e:
    print(f"Error reading database: {e}")
