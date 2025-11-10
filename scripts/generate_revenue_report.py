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
OUTPUT_FILENAME = "revenue_report_arabic.xlsx"  # Changed filename for the Arabic report

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
    Generates a comprehensive and detailed revenue report in Arabic and saves it as an Excel file.
    """
    print("Starting Arabic revenue report generation...")

    with get_db() as db:
        # --- Data Extraction ---
        print("Extracting data from the database...")

        query = (
            db.query(
                User.telegram_user_id,
                User.first_name,
                User.last_name,
                Course.course_name,
                Course.price.label("course_base_price"),
                Course.certificate_price,
                Enrollment.enrollment_date,
                Enrollment.amount_paid,
                Enrollment.with_certificate
            )
            .join(Enrollment, User.user_id == Enrollment.user_id)
            .join(Course, Enrollment.course_id == Course.course_id)
            .filter(Enrollment.payment_status == PaymentStatus.VERIFIED)
        )
        
        verified_enrollments = query.all()

        if not verified_enrollments:
            print("No verified enrollments found to generate a report.")
            return

        # --- DataFrame with Arabic Headers ---
        df = pd.DataFrame(verified_enrollments, columns=[
            "معرف المستخدم (تليجرام)", "الاسم الأول", "اسم العائلة", "اسم الدورة", "سعر الدورة الأساسي",
            "سعر الشهادة", "تاريخ التسجيل", "المبلغ المدفوع", "مع شهادة"
        ])

        # --- Data Processing and Analysis ---
        print("Processing and analyzing data...")

        total_revenue = df["المبلغ المدفوع"].sum()

        revenue_by_course = df.groupby("اسم الدورة")["المبلغ المدفوع"].sum().reset_index()
        revenue_by_course = revenue_by_course.rename(columns={"المبلغ المدفوع": "إجمالي الإيرادات"})

        enrollment_details = df.groupby("اسم الدورة")['مع شهادة'].value_counts().unstack(fill_value=0)
        if True not in enrollment_details:
            enrollment_details[True] = 0
        if False not in enrollment_details:
            enrollment_details[False] = 0
        enrollment_details.rename(columns={True: 'مع شهادة', False: 'بدون شهادة'}, inplace=True)
        enrollment_details['إجمالي المسجلين'] = enrollment_details['مع شهادة'] + enrollment_details['بدون شهادة']
        enrollment_details = enrollment_details.reset_index()

        df["شهر التسجيل"] = pd.to_datetime(df["تاريخ التسجيل"]).dt.to_period('M')
        revenue_by_month = df.groupby("شهر التسجيل")["المبلغ المدفوع"].sum().reset_index()
        revenue_by_month["شهر التسجيل"] = revenue_by_month["شهر التسجيل"].astype(str)

        df['إيرادات من الشهادات'] = df.apply(lambda row: row['سعر الشهادة'] if row['مع شهادة'] else 0, axis=1)
        total_certificate_revenue = df['إيرادات من الشهادات'].sum()
        total_course_revenue = total_revenue - total_certificate_revenue

        # --- Excel Generation ---
        print("Generating detailed Excel report in Arabic...")

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILENAME)

        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # Summary Sheet
            summary_data = {
                "المقياس": [
                    "إجمالي الإيرادات",
                    "إيرادات الدورات (السعر الأساسي)",
                    "إيرادات الشهادات",
                    "إجمالي التسجيلات المؤكدة",
                    "إجمالي الدورات المقدمة"
                ],
                "القيمة": [
                    f"${total_revenue:,.2f}",
                    f"${total_course_revenue:,.2f}",
                    f"${total_certificate_revenue:,.2f}",
                    len(df),
                    df["اسم الدورة"].nunique()
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name="ملخص", index=False)

            # Detailed Enrollments Sheet
            df.to_excel(writer, sheet_name="التسجيلات المؤكدة", index=False)

            # Enrollment Breakdown Sheet
            enrollment_details.to_excel(writer, sheet_name="تفاصيل التسجيل", index=False)

            # Revenue by Course Sheet
            revenue_by_course.to_excel(writer, sheet_name="الإيرادات حسب الدورة", index=False)

            # Revenue by Month Sheet
            revenue_by_month.to_excel(writer, sheet_name="الإيرادات حسب الشهر", index=False)

        print(f"Detailed Arabic revenue report successfully generated at: {output_path}")


if __name__ == "__main__":
    generate_revenue_report()