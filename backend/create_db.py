"""
Quick script to create the crypto_bot database
"""
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Connect to PostgreSQL server (not to a specific database)
try:
    conn = psycopg2.connect(
        host="127.0.0.1",
        port=5432,
        user="postgres",
        password="postgres"
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    
    # Check if database exists
    cursor.execute("SELECT 1 FROM pg_database WHERE datname='crypto_bot'")
    exists = cursor.fetchone()
    
    if exists:
        print("✅ Database 'crypto_bot' already exists")
    else:
        # Create database
        cursor.execute("CREATE DATABASE crypto_bot")
        print("✅ Database 'crypto_bot' created successfully")
    
    cursor.close()
    conn.close()
    
    print("\nNow initializing tables...")
    from database_pg import init_pg_db
    init_pg_db()
    
except Exception as e:
    print(f"❌ Error: {e}")
    print("\nMake sure PostgreSQL is running and credentials are correct:")
    print("  Host: 127.0.0.1")
    print("  Port: 5432")
    print("  User: postgres")
    print("  Password: postgres")
