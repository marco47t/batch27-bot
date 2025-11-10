import os
import sys
import pandas as pd
from datetime import datetime

# Add the project root to the sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from database.models import User, Course, Enrollment, Transaction, PaymentStatus
from contextlib import contextmanager
import config

# --- Configuration ---
DATABASE_URL = config.DATABASE_URL
OUTPUT_DIR = "receipts"
OUTPUT_FILENAME = "revenue_report.xlsx"

# --- Database Setup ---
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@contextmanager
def get_db():
    """Provides a transactional scope around a series of operations."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def generate_revenue_report():
    """
    Generates a comprehensive revenue report from the database and saves it as an Excel file.
    """
    print("Starting revenue report generation...")

    with get_db() as db:
        # --- Data Extraction ---
        print("Extracting data from the database...")

        # Query for verified enrollments and their associated transactions
        verified_enrollments = (
            db.query(
                User.telegram_user_id,
                User.first_name,
                User.last_name,
                Course.course_name,
                Course.price,
                Enrollment.enrollment_date,
                Enrollment.amount_paid,
                Enrollment.with_certificate,
                Transaction.submitted_date,
                Transaction.receipt_amount
            )
            .join(Enrollment, User.user_id == Enrollment.user_id)
            .join(Course, Enrollment.course_id == Course.course_id)
            .join(Transaction, Enrollment.enrollment_id == Transaction.enrollment_id)
            .filter(Enrollment.payment_status == PaymentStatus.VERIFIED)
            .all()
        )

        if not verified_enrollments:
            print("No verified enrollments found to generate a report.")
            return

        # Convert to pandas DataFrame
        df = pd.DataFrame(verified_enrollments, columns=[
            "Telegram User ID", "First Name", "Last Name", "Course Name", "Course Price",
            "Enrollment Date", "Amount Paid", "With Certificate",
            "Transaction Submitted Date", "Receipt Amount"
        ])

        # --- Data Processing and Analysis ---
        print("Processing and analyzing data...")

        # 1. Total Revenue
        total_revenue = df["Amount Paid"].sum()

        # 2. Revenue per Course
        revenue_by_course = df.groupby("Course Name")["Amount Paid"].sum().reset_index()
        revenue_by_course = revenue_by_course.rename(columns={"Amount Paid": "Total Revenue"})

        # 3. Number of Enrollments per Course
        enrollments_by_course = df.groupby("Course Name").size().reset_index(name="Number of Enrollments")

        # 4. Revenue by Month
        df["Enrollment Month"] = df["Enrollment Date"].dt.to_period('M')
        revenue_by_month = df.groupby("Enrollment Month")["Amount Paid"].sum().reset_index()
        revenue_by_month["Enrollment Month"] = revenue_by_month["Enrollment Month"].astype(str) # Convert period to string for Excel

        # --- Excel Generation ---
        print("Generating Excel report...")

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILENAME)

        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # Summary Sheet
            summary_data = {
                "Metric": [
                    "Total Revenue",
                    "Total Verified Enrollments",
                    "Number of Courses"
                ],
                "Value": [
                    f"${total_revenue:,.2f}",
                    len(df),
                    df["Course Name"].nunique()
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name="Summary", index=False)

            # Detailed Transactions Sheet
            df.to_excel(writer, sheet_name="Verified Transactions", index=False)

            # Revenue by Course Sheet
            revenue_by_course.to_excel(writer, sheet_name="Revenue by Course", index=False)

            # Enrollments by Course Sheet
            enrollments_by_course.to_excel(writer, sheet_name="Enrollments by Course", index=False)

            # Revenue by Month Sheet
            revenue_by_month.to_excel(writer, sheet_name="Revenue by Month", index=False)


        print(f"Revenue report successfully generated at: {output_path}")


if __name__ == "__main__":
    generate_revenue_report()
