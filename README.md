# Discord Standup Bot

A production-ready Discord bot for collecting daily standups from team members, with AI-powered summaries using Google Gemini.

## Features

### For Team Members
- **Opt-in Registration**: Users register for standups with `/register`
- **Structured Questions**: Fixed 4-question format for consistency
  - What did you work on yesterday?
  - What are you working on today?
  - Any blockers?
  - Confidence/mood (1-5, optional)
- **Progress Saving**: Answers saved as you go, resume if interrupted
- **Edit Responses**: Modify answers within the collection window
- **No Update Option**: Quickly mark "no update" for a day

### For Admins
- **Configurable Schedule**: Set collection times and timezone
- **Summary Channel**: Choose where daily summaries are posted
- **Non-Responder Visibility**: Easily see who hasn't responded
- **AI Summaries**: Grouped by theme, with blockers and risks highlighted
- **Manual Controls**: Trigger collection or reminders on demand

## Commands

### User Commands
| Command | Description |
|---------|-------------|
| `/register` | Sign up for daily standups |
| `/unregister` | Opt out of standups |
| `/my_status` | Check your registration and response status |
| `/no_update` | Mark no update for today |
| `/edit_standup` | Edit your response within the window |

### Admin Commands
| Command | Description |
|---------|-------------|
| `/config` | View all configuration |
| `/status [date]` | View response statistics |
| `/missing [date]` | List non-responders |
| `/responses [date]` | View all responses |
| `/summary [date]` | Generate AI summary |
| `/collect_now` | Trigger collection manually |
| `/remind_now` | Send reminders to non-responders |
| `/set_time` | Set collection window |
| `/set_timezone` | Set timezone |
| `/set_summary_channel` | Set summary output channel |
| `/list_users` | View registered users |
| `/standup_help` | Show all commands |

## Setup

### Prerequisites
- Python 3.10+
- A Discord bot token
- A Gemini API key
- A Turso database

### 1. Create Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to "Bot" section, create a bot
4. Copy the token
5. Enable these intents:
   - Presence Intent
   - Server Members Intent
   - Message Content Intent
6. Generate invite URL with permissions:
   - Send Messages
   - Read Messages/View Channels
   - Embed Links
   - Use Slash Commands
   - Read Message History

### 2. Create Turso Database

1. Sign up at [Turso](https://turso.tech/)
2. Create a new database
3. Get your database URL and auth token

### 3. Get Gemini API Key

1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Create an API key

### 4. Configure Environment

```bash
# Copy template
cp .env.template .env

# Edit with your values
nano .env
```

Fill in:
- `DISCORD_TOKEN` - Your bot token
- `GUILD_ID` - Your server ID (right-click server → Copy ID)
- `GEMINI_API_KEY` - Your Gemini API key
- `DATABASE_URL` - Your Turso database URL
- `DATABASE_TOKEN` - Your Turso auth token

### 5. Install Dependencies

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install packages
pip install -r requirements.txt
```

### 6. Run the Bot

```bash
python bot.py
```

## Deployment

### Option 1: Cloud VM (Recommended)

Deploy to any cloud provider (AWS, GCP, Azure, DigitalOcean):

```bash
# Clone repository
git clone <your-repo>
cd discord-bot

# Setup
cp .env.template .env
# Edit .env with your values

# Install
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run with screen/tmux for persistence
screen -S standup-bot
python bot.py
# Detach with Ctrl+A, D
```

### Option 2: Railway/Render

1. Connect your GitHub repository
2. Set environment variables in the dashboard
3. Deploy

### Option 3: Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "bot.py"]
```

```bash
docker build -t standup-bot .
docker run --env-file .env standup-bot
```

## How It Works

### Collection Flow

1. **Start Time**: Bot DMs registered users with standup questions
2. **Collection Window**: Users answer at their own pace
3. **Midpoint**: Reminder sent to non-responders (once only)
4. **End Time**: AI summary generated and posted

### Standup Date Logic

For windows spanning midnight (e.g., 22:00-02:00):
- Responses after midnight count toward the previous day's standup
- Summary is posted at window end with correct date

### Data Storage

All data is stored in Turso (SQLite-compatible):
- `registered_users` - Who receives standups
- `responses` - Complete standup responses
- `partial_responses` - In-progress standups
- `settings` - Bot configuration

## Architecture

```
discord-bot/
├── bot.py              # Main entry point
├── database.py         # Database operations
├── gemini_client.py    # AI summary generation
├── cogs/
│   ├── registration.py # User registration
│   ├── collection.py   # DM collection flow
│   ├── admin.py        # Admin commands
│   └── scheduler.py    # Automated scheduling
├── .env.template       # Environment template
└── requirements.txt    # Dependencies
```

## Troubleshooting

### Bot doesn't respond to commands
- Check if slash commands are synced (restart bot)
- Verify `GUILD_ID` is correct
- Check bot has proper permissions

### DMs not sending
- Users may have DMs disabled
- Check bot has DM permissions
- Rate limiting may apply

### Summary not posting
- Ensure summary channel is set with `/set_summary_channel`
- Check bot has permission in that channel

### Database errors
- Verify `DATABASE_URL` and `DATABASE_TOKEN`
- Check Turso dashboard for connection issues

## License

MIT
