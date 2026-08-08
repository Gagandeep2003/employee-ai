from motor.motor_asyncio import AsyncIOMotorClient

import config

client = AsyncIOMotorClient(config.MONGO_URL)
db = client[config.DB_NAME]

# Collection references for type hints and direct access
users = db.users
businesses = db.businesses
knowledge_chunks = db.knowledge_chunks
conversations = db.conversations
messages = db.messages
sessions = db.sessions
login_events = db.login_events
audit_logs = db.audit_logs
api_keys = db.api_keys
referrals = db.referrals
invoices = db.invoices
subscriptions = db.subscriptions
platform_settings = db.platform_settings
legal_pages = db.legal_pages
appointment_bookings = db.appointment_bookings
notifications = db.notifications
support_tickets = db.support_tickets
sales_representatives = db.sales_representatives
password_reset_otps = db.password_reset_otps
