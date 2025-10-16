"""
Simple script to view database contents
"""

import sqlite3
from tabulate import tabulate

def view_all_tables():
    """Display all data from all tables"""
    conn = sqlite3.connect('course_bot.db')
    cursor = conn.cursor()
    
    # Get all table names
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    for table in tables:
        table_name = table[0]
        print(f"\n{'='*80}")
        print(f"TABLE: {table_name}")
        print('='*80)
        
        # Get all data from table
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()
        
        # Get column names
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [column[1] for column in cursor.fetchall()]
        
        if rows:
            print(tabulate(rows, headers=columns, tablefmt='grid'))
        else:
            print("(No data)")
    
    conn.close()

def view_statistics():
    """Display database statistics"""
    conn = sqlite3.connect('course_bot.db')
    cursor = conn.cursor()
    
    print("\n" + "="*80)
    print("DATABASE STATISTICS")
    print("="*80)
    
    # User count
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]
    print(f"📊 Total Users: {user_count}")
    
    # Course count
    cursor.execute("SELECT COUNT(*) FROM courses")
    course_count = cursor.fetchone()[0]
    print(f"📚 Total Courses: {course_count}")
    
    # Enrollment counts by status
    cursor.execute("SELECT payment_status, COUNT(*) FROM enrollments GROUP BY payment_status")
    enrollments = cursor.fetchall()
    print(f"\n💳 Enrollments by Status:")
    for status, count in enrollments:
        print(f"   - {status}: {count}")
    
    # Transaction counts
    cursor.execute("SELECT status, COUNT(*) FROM transactions GROUP BY status")
    transactions = cursor.fetchall()
    print(f"\n📋 Transactions by Status:")
    for status, count in transactions:
        print(f"   - {status}: {count}")
    
    # Revenue
    cursor.execute("SELECT SUM(payment_amount) FROM enrollments WHERE payment_status='VERIFIED'")
    revenue = cursor.fetchone()[0] or 0
    print(f"\n💰 Total Revenue: ${revenue:.2f}")
    
    conn.close()

if __name__ == "__main__":
    # Install tabulate first: pip install tabulate
    view_statistics()
    print("\n\nPress Enter to view all tables...")
    input()
    view_all_tables()
