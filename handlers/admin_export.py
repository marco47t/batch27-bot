"""
Admin data export and analytics dashboard
"""
from telegram import Update
from telegram.ext import ContextTypes
from database import crud, get_db
from database.models import PaymentStatus, TransactionStatus, CourseReview
from utils.helpers import is_admin_user
from datetime import datetime
import csv
import io
import logging

logger = logging.getLogger(__name__)


# ==================== EXPORT ENROLLMENTS ====================

async def export_enrollments_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Export all enrollments to CSV - Admin only"""
    user = update.effective_user
    
    if not is_admin_user(user.id):
        await update.message.reply_text("❌ Admin access only.")
        return
    
    await update.message.reply_text("📊 Generating enrollment data export...\n\nPlease wait...")
    
    try:
        with get_db() as session:
            enrollments = session.query(crud.Enrollment).all()
            
            if not enrollments:
                await update.message.reply_text("📭 No enrollment data to export.")
                return
            
            # Create CSV
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Headers
            writer.writerow([
                'Enrollment ID', 'User ID', 'Telegram ID', 'Name', 'Username',
                'Course ID', 'Course Name', 'Price', 'Payment Status',
                'Enrollment Date', 'Verification Date'
            ])
            
            # Data rows
            for enrollment in enrollments:
                writer.writerow([
                    enrollment.enrollment_id,
                    enrollment.user_id,
                    enrollment.user.telegram_user_id,
                    f"{enrollment.user.first_name} {enrollment.user.last_name or ''}".strip(),
                    enrollment.user.username or 'N/A',
                    enrollment.course_id,
                    enrollment.course.course_name,
                    enrollment.payment_amount or 0,
                    enrollment.payment_status.value,
                    enrollment.enrollment_date.strftime('%Y-%m-%d %H:%M'),
                    enrollment.verification_date.strftime('%Y-%m-%d %H:%M') if enrollment.verification_date else 'N/A'
                ])
            
            # Send file
            output.seek(0)
            filename = f"enrollments_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            await update.message.reply_document(
                document=output.getvalue().encode('utf-8'),
                filename=filename,
                caption=f"📊 **Enrollment Data Export**\n\n"
                       f"✅ Total Enrollments: {len(enrollments)}\n"
                       f"📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                parse_mode='Markdown'
            )
            
            logger.info(f"Admin {user.id} exported {len(enrollments)} enrollments")
            
    except Exception as e:
        logger.error(f"Failed to export enrollments: {e}")
        await update.message.reply_text(f"❌ Export failed: {str(e)}")


# ==================== EXPORT TRANSACTIONS ====================

async def export_transactions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Export all transactions to CSV - Admin only"""
    user = update.effective_user
    
    if not is_admin_user(user.id):
        await update.message.reply_text("❌ Admin access only.")
        return
    
    await update.message.reply_text("📊 Generating transaction data export...\n\nPlease wait...")
    
    try:
        with get_db() as session:
            transactions = session.query(crud.Transaction).all()
            
            if not transactions:
                await update.message.reply_text("📭 No transaction data to export.")
                return
            
            # Create CSV
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Headers
            writer.writerow([
                'Transaction ID', 'Enrollment ID', 'User Name', 'Course Name',
                'Amount', 'Status', 'Submitted Date', 'Review Date', 'Fraud Score'
            ])
            
            # Data rows
            for transaction in transactions:
                enrollment = transaction.enrollment
                writer.writerow([
                    transaction.transaction_id,
                    transaction.enrollment_id,
                    f"{enrollment.user.first_name} {enrollment.user.last_name or ''}".strip(),
                    enrollment.course.course_name,
                    transaction.extracted_amount or 0,
                    transaction.status.value,
                    transaction.submitted_date.strftime('%Y-%m-%d %H:%M'),
                    transaction.admin_review_date.strftime('%Y-%m-%d %H:%M') if transaction.admin_review_date else 'N/A',
                    transaction.fraud_score
                ])
            
            # Send file
            output.seek(0)
            filename = f"transactions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            await update.message.reply_document(
                document=output.getvalue().encode('utf-8'),
                filename=filename,
                caption=f"💳 **Transaction Data Export**\n\n"
                       f"✅ Total Transactions: {len(transactions)}\n"
                       f"📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                parse_mode='Markdown'
            )
            
            logger.info(f"Admin {user.id} exported {len(transactions)} transactions")
            
    except Exception as e:
        logger.error(f"Failed to export transactions: {e}")
        await update.message.reply_text(f"❌ Export failed: {str(e)}")


# ==================== GENERATE ANALYTICS DASHBOARD ====================

async def generate_dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate comprehensive HTML analytics dashboard - Admin only"""
    user = update.effective_user
    
    if not is_admin_user(user.id):
        await update.message.reply_text("❌ Admin access only.")
        return
    
    await update.message.reply_text("📊 Generating analytics dashboard...\n\nPlease wait...")
    
    try:
        with get_db() as session:
            # Gather statistics
            enrollments = session.query(crud.Enrollment).all()
            courses = crud.get_all_courses(session)
            reviews = session.query(CourseReview).all()
            students = crud.get_all_active_students(session)
            
            # Calculate stats
            total_enrollments = len(enrollments)
            verified_enrollments = sum(1 for e in enrollments if e.payment_status == PaymentStatus.VERIFIED)
            pending_enrollments = sum(1 for e in enrollments if e.payment_status == PaymentStatus.PENDING)
            total_revenue = sum(e.payment_amount or 0 for e in enrollments if e.payment_status == PaymentStatus.VERIFIED)
            total_reviews = len(reviews)
            avg_rating = round(sum(r.rating for r in reviews) / len(reviews), 1) if reviews else 0
            total_students = len(students)
            
            # Course data for charts
            course_data = []
            for course in courses:
                course_enrollments = [e for e in enrollments if e.course_id == course.course_id and e.payment_status == PaymentStatus.VERIFIED]
                course_revenue = sum(e.payment_amount or 0 for e in course_enrollments)
                course_reviews = [r for r in reviews if r.course_id == course.course_id]
                course_rating = round(sum(r.rating for r in course_reviews) / len(course_reviews), 1) if course_reviews else 0
                
                course_data.append({
                    'name': course.course_name,
                    'enrollments': len(course_enrollments),
                    'revenue': course_revenue,
                    'rating': course_rating,
                    'reviews': len(course_reviews)
                })
            
            # Generate HTML dashboard
            html_content = generate_html_dashboard(
                total_enrollments=total_enrollments,
                verified_enrollments=verified_enrollments,
                pending_enrollments=pending_enrollments,
                total_revenue=total_revenue,
                total_reviews=total_reviews,
                avg_rating=avg_rating,
                total_students=total_students,
                course_data=course_data
            )
            
            # Send HTML file
            filename = f"dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            
            await update.message.reply_document(
                document=html_content.encode('utf-8'),
                filename=filename,
                caption=f"📊 **Analytics Dashboard**\n\n"
                       f"📈 Total Students: {total_students}\n"
                       f"📚 Total Enrollments: {total_enrollments}\n"
                       f"💰 Total Revenue: ${total_revenue:,.2f}\n"
                       f"⭐ Average Rating: {avg_rating}/5\n"
                       f"📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                       f"📥 Download and open in browser",
                parse_mode='Markdown'
            )
            
            logger.info(f"Admin {user.id} generated analytics dashboard")
            
    except Exception as e:
        logger.error(f"Failed to generate dashboard: {e}")
        await update.message.reply_text(f"❌ Dashboard generation failed: {str(e)}")


def generate_html_dashboard(total_enrollments, verified_enrollments, pending_enrollments,
                            total_revenue, total_reviews, avg_rating, total_students, course_data):
    """Generate HTML dashboard with Chart.js visualizations"""
    
    # Extract data for charts
    course_names = [c['name'] for c in course_data]
    course_enrollments = [c['enrollments'] for c in course_data]
    course_revenues = [c['revenue'] for c in course_data]
    course_ratings = [c['rating'] for c in course_data]
    course_review_counts = [c['reviews'] for c in course_data]
    
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Course Registration Bot - Analytics Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        .header {{
            text-align: center;
            color: white;
            margin-bottom: 30px;
        }}
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        .header p {{
            font-size: 1.1em;
            opacity: 0.9;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: white;
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            transition: transform 0.3s;
        }}
        .stat-card:hover {{
            transform: translateY(-5px);
        }}
        .stat-card .icon {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        .stat-card .value {{
            font-size: 2em;
            font-weight: bold;
            color: #667eea;
            margin: 10px 0;
        }}
        .stat-card .label {{
            color: #666;
            font-size: 0.9em;
        }}
        .charts-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .chart-card {{
            background: white;
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }}
        .chart-card h3 {{
            margin-bottom: 20px;
            color: #333;
        }}
        .table-container {{
            background: white;
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            overflow-x: auto;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background: #667eea;
            color: white;
            font-weight: bold;
        }}
        tr:hover {{
            background: #f5f5f5;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Course Registration Analytics</h1>
            <p>Generated on {datetime.now().strftime('%B %d, %Y at %H:%M')}</p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="icon">👥</div>
                <div class="value">{total_students}</div>
                <div class="label">Total Students</div>
            </div>
            <div class="stat-card">
                <div class="icon">📚</div>
                <div class="value">{verified_enrollments}</div>
                <div class="label">Verified Enrollments</div>
            </div>
            <div class="stat-card">
                <div class="icon">⏳</div>
                <div class="value">{pending_enrollments}</div>
                <div class="label">Pending Enrollments</div>
            </div>
            <div class="stat-card">
                <div class="icon">💰</div>
                <div class="value">${total_revenue:,.0f}</div>
                <div class="label">Total Revenue</div>
            </div>
            <div class="stat-card">
                <div class="icon">⭐</div>
                <div class="value">{avg_rating}/5</div>
                <div class="label">Average Rating</div>
            </div>
            <div class="stat-card">
                <div class="icon">💬</div>
                <div class="value">{total_reviews}</div>
                <div class="label">Total Reviews</div>
            </div>
        </div>
        
        <div class="charts-grid">
            <div class="chart-card">
                <h3>📊 Enrollments by Course</h3>
                <canvas id="enrollmentsChart"></canvas>
            </div>
            <div class="chart-card">
                <h3>💰 Revenue by Course</h3>
                <canvas id="revenueChart"></canvas>
            </div>
            <div class="chart-card">
                <h3>⭐ Ratings by Course</h3>
                <canvas id="ratingsChart"></canvas>
            </div>
            <div class="chart-card">
                <h3>💬 Reviews by Course</h3>
                <canvas id="reviewsChart"></canvas>
            </div>
        </div>
        
        <div class="table-container">
            <h3>📚 Course Details</h3>
            <table>
                <thead>
                    <tr>
                        <th>Course Name</th>
                        <th>Enrollments</th>
                        <th>Revenue</th>
                        <th>Rating</th>
                        <th>Reviews</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(f"<tr><td>{c['name']}</td><td>{c['enrollments']}</td><td>${c['revenue']:,.2f}</td><td>{c['rating']}⭐</td><td>{c['reviews']}</td></tr>" for c in course_data)}
                </tbody>
            </table>
        </div>
    </div>
    
    <script>
        const courseNames = {course_names};
        const courseEnrollments = {course_enrollments};
        const courseRevenues = {course_revenues};
        const courseRatings = {course_ratings};
        const courseReviews = {course_review_counts};
        
        // Enrollments Chart
        new Chart(document.getElementById('enrollmentsChart'), {{
            type: 'bar',
            data: {{
                labels: courseNames,
                datasets: [{{
                    label: 'Enrollments',
                    data: courseEnrollments,
                    backgroundColor: 'rgba(102, 126, 234, 0.6)',
                    borderColor: 'rgba(102, 126, 234, 1)',
                    borderWidth: 2
                }}]
            }},
            options: {{
                responsive: true,
                scales: {{
                    y: {{
                        beginAtZero: true
                    }}
                }}
            }}
        }});
        
        // Revenue Chart
        new Chart(document.getElementById('revenueChart'), {{
            type: 'doughnut',
            data: {{
                labels: courseNames,
                datasets: [{{
                    data: courseRevenues,
                    backgroundColor: [
                        'rgba(255, 99, 132, 0.6)',
                        'rgba(54, 162, 235, 0.6)',
                        'rgba(255, 206, 86, 0.6)',
                        'rgba(75, 192, 192, 0.6)',
                        'rgba(153, 102, 255, 0.6)'
                    ]
                }}]
            }},
            options: {{
                responsive: true
            }}
        }});
        
        // Ratings Chart
        new Chart(document.getElementById('ratingsChart'), {{
            type: 'radar',
            data: {{
                labels: courseNames,
                datasets: [{{
                    label: 'Rating',
                    data: courseRatings,
                    backgroundColor: 'rgba(255, 159, 64, 0.2)',
                    borderColor: 'rgba(255, 159, 64, 1)',
                    borderWidth: 2
                }}]
            }},
            options: {{
                responsive: true,
                scales: {{
                    r: {{
                        beginAtZero: true,
                        max: 5
                    }}
                }}
            }}
        }});
        
        // Reviews Chart
        new Chart(document.getElementById('reviewsChart'), {{
            type: 'pie',
            data: {{
                labels: courseNames,
                datasets: [{{
                    data: courseReviews,
                    backgroundColor: [
                        'rgba(255, 99, 132, 0.6)',
                        'rgba(54, 162, 235, 0.6)',
                        'rgba(255, 206, 86, 0.6)',
                        'rgba(75, 192, 192, 0.6)',
                        'rgba(153, 102, 255, 0.6)'
                    ]
                }}]
            }},
            options: {{
                responsive: true
            }}
        }});
    </script>
</body>
</html>
"""
