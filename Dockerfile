FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY bot.py database.py scoring.py config.py club_emblems.py casino.py fut.py ./

# Run the bot in polling mode
CMD ["python", "bot.py"]
