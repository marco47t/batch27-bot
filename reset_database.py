"""
Reset Database - Clear all data for production deployment
WARNING: This will DELETE ALL DATA from all tables!
"""
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    print("❌ DATABASE_URL not found in .env file")
    exit(1)

print("⚠️  WARNING: This will DELETE ALL DATA from your database!")
print("=" * 60)

# Ask for confirmation
confirmation = input("Type 'DELETE ALL DATA' to confirm: ")

if confirmation != "DELETE ALL DATA":
    print("❌ Operation cancelled.")
    exit(0)

print("\n🔄 Connecting to database...")

try:
    engine = create_engine(DATABASE_URL)

    with engine.connect() as connection:
        trans = connection.begin()

        try:
            print("\n🗑️  Deleting data from all tables...")

            # FIXED: Delete in correct order (respecting foreign keys)
            # Child tables first, then parent tables
            tables_to_clear = [
                "transactions",           # No dependencies
                "course_reviews",         # References enrollments (DELETE FIRST!)
                "enrollments",            # References courses and users
                "notification_preferences",  # References users
                "shopping_cart",          # References courses and users  
                "courses",                # Parent table
                "users"                   # Parent table (last!)
            ]

            for table in tables_to_clear:
                result = connection.execute(text(f"DELETE FROM {table}"))
                print(f"   ✅ Cleared {table}: {result.rowcount} rows deleted")

            # Reset auto-increment sequences
            print("\n🔄 Resetting auto-increment sequences...")
            sequences = [
                ("users", "user_id"),
                ("courses", "course_id"),
                ("enrollments", "enrollment_id"),
                ("transactions", "transaction_id"),
                ("course_reviews", "review_id"),
                ("notification_preferences", "preference_id"),
                ("shopping_cart", "id")
            ]

            for table, column in sequences:
                try:
                    connection.execute(text(f"ALTER SEQUENCE {table}_{column}_seq RESTART WITH 1"))
                    print(f"   ✅ Reset sequence: {table}_{column}_seq")
                except Exception as e:
                    print(f"   ⚠️  Could not reset {table}_{column}_seq (may not exist): {e}")

            trans.commit()

            print("\n" + "=" * 60)
            print("✅ DATABASE SUCCESSFULLY CLEARED!")
            print("=" * 60)
            print("\n📊 Database is now ready for production deployment.")
            print("\nNext steps:")
            print("1. Start the bot: python main.py")
            print("2. Register admin: /register_admin <password>")
            print("3. Add courses: /addcourse")
            print("\n⚠️  Note: S3 receipt files (if any) were NOT deleted.")
            print("   Delete them manually from AWS S3 console if needed.")

        except Exception as e:
            trans.rollback()
            print(f"\n❌ Error during deletion: {e}")
            import traceback
            traceback.print_exc()

except Exception as e:
    print(f"\n❌ Connection failed: {e}")
    import traceback
    traceback.print_exc()
