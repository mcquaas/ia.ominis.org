# Ominis Live Avatar (Pipecat + BioMistral)

Pipecat Cloud agent that uses Ominis backend (BioMistral/ominis-2.0-clinic) instead of HeyGen's LLM.

## Prerequisites

- Python 3.12 (pipecatcloud does not work on Python 3.14)
- Docker Hub account
- Pipecat Cloud account: https://pipecat.ai
- API keys: HeyGen Live Avatar, Deepgram, Cartesia

## Setup

```bash
# 1. Create venv with Python 3.12
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pipecatcloud

# 2. Secrets
cp .env.pipecat.example .env.pipecat
# Edit .env.pipecat with your keys:
#   HEYGEN_LIVE_AVATAR_API_KEY, DEEPGRAM_API_KEY, CARTESIA_API_KEY
#   OMINIS_BACKEND_URL=https://api.ominis.org/v1/liveavatar

# 3. Docker image
# Edit pcc-deploy.toml: replace YOUR_DOCKERHUB_USER

# 4. Login
pcc auth login
docker login  # if needed for push
```

## Deploy

```bash
# From project root
./infrastructure/23-deploy-liveavatar-pipecat.sh
```

Or manually:

```bash
source .venv/bin/activate
pcc secrets set ominis-live-avatar-secrets --file .env.pipecat --skip
pcc docker build-push
pcc deploy --force
```

## Backend configuration

Add to backend `.env`:

```
PIPECAT_AGENT_NAME=ominis-live-avatar
PIPECAT_API_TOKEN=<from Pipecat Cloud dashboard>
```
