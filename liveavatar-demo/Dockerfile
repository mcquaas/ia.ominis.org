FROM dailyco/pipecat-base:latest

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py main.py
COPY bot.py bot.py
