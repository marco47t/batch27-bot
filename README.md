# Batch27 Telegram Course Registration Bot

A comprehensive Telegram bot for managing course registrations, payments, and student management.

## Features

- 📚 Course management with dates and pricing
- 💳 Payment processing with receipt verification
- 🤖 AI-powered fraud detection using Gemini
- 👥 Automatic Telegram group management
- 📊 Admin dashboard and analytics
- ⭐ Student review system
- 📧 Automated notifications
- 🔐 Secure payment verification

## Tech Stack

- **Language:** Python 3.11+
- **Framework:** python-telegram-bot
- **Database:** PostgreSQL
- **Storage:** AWS S3
- **AI:** Google Gemini API
- **Deployment:** AWS EC2 + RDS

## Installation

### Prerequisites

- Python 3.11 or higher
- PostgreSQL database
- AWS S3 bucket
- Telegram Bot Token
- Gemini API Key

### Setup

1. Clone the repository:
```bash
git clone https://github.com/YOUR_USERNAME/batch27-bot.git
cd batch27-bot
```

2. Create virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment:
```bash
cp .env.example .env
# Edit .env with your actual credentials
```

5. Initialize database:
```bash
python -c "from database import init_db; init_db()"
python database/migrate_add_amount_paid.py
python database/migrate_add_reviews_prefs.py
```

6. Run the bot:
```bash
python main.py
```

## Deployment

### AWS EC2 + RDS

See [AWS_STEP_BY_STEP_GUIDE.md](AWS_STEP_BY_STEP_GUIDE.md) for complete deployment instructions.

## Configuration

All configuration is done through environment variables. See `.env.example` for required variables.

## Project Structure

```
batch27-bot/
├── handlers/           # Telegram bot handlers
├── database/          # Database models and CRUD operations
├── utils/             # Helper functions and utilities
├── fraud_detection/   # Receipt fraud detection
├── main.py           # Bot entry point
├── config.py         # Configuration management
└── requirements.txt  # Python dependencies
```

## Admin Commands

- `/admin` - Access admin dashboard
- `/addcourse` - Add new course
- `/pending_registrations` - View pending enrollments
- `/adminhelp` - View all admin commands

## License

Private project - All rights reserved

## Support

For issues or questions, contact the development team.
