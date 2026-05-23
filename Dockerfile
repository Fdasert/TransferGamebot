FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY bot.py database.py scoring.py config.py club_emblems.py casino.py fut.py patch_notes.py ./

# Render sets PORT=10000; expose it for the health-check server
EXPOSE 10000

# Run the bot in polling mode
CMD ["python", "bot.py"]
