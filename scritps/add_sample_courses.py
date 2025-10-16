from database import get_db, crud

sample_courses = [
    {
        "name": "Python Fullstack Bootcamp",
        "description": "Learn backend and frontend development with Python, JS, and modern frameworks.",
        "price": 200.0,
        "telegram_group_link": "https://t.me/joinchat/PythonBootcampSample",
        "telegram_group_id": 100001,
        "max_students": 30
    },
    {
        "name": "Telegram Bot Mastery",
        "description": "Build advanced Telegram bots using Python and async Telegram APIs.",
        "price": 120.0,
        "telegram_group_link": "https://t.me/joinchat/BotMasterySample",
        "telegram_group_id": 100002,
        "max_students": 25
    },
    {
        "name": "Introduction to AI APIs",
        "description": "Discover AI-powered APIs for NLP, computer vision, and chatbots.",
        "price": 150.0,
        "telegram_group_link": "https://t.me/joinchat/AIApiSample",
        "telegram_group_id": 100003,
        "max_students": 40
    }
]

with get_db() as session:
    for course in sample_courses:
        crud.create_course(
            session,
            course_name=course["name"],
            description=course["description"],
            price=course["price"],
            telegram_group_link=course["telegram_group_link"],
            telegram_group_id=course["telegram_group_id"],
            max_students=course["max_students"]
        )
    print("✓ Sample courses added!")
