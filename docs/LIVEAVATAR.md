# LiveAvatar + Ominis Clinical LLM

Integration of HeyGen LiveAvatar with Ominis 2.0 Clinic (BioMistral) for real-time voice conversations.

## Page: /live (ia.ominis.org/live)

Standalone page at `/live` with its own layout — does not use the main chat UI.

- **Layout**: Minimal header with logo, "Ir al chat" link, Live Avatar label
- **Flow**: User clicks "Iniciar sesión con avatar" → backend creates HeyGen session → opens LiveKit meet URL in new window
- **Mode**: FULL (HeyGen LLM) by default. For clinical LLM, use Pipecat + `liveavatar-demo/`

## Overview

- **LiveAvatar**: HeyGen's real-time AI avatar (WebRTC, lip-sync, expressions)
- **Pipecat**: Speech-to-speech pipeline (STT → LLM → TTS → avatar)
- **Ominis proxy**: OpenAI-compatible endpoint that routes to the full clinical pipeline (RAG, PubMed, BioMistral, clinical validation)

## Modes

| Mode | LLM | Config |
|------|-----|--------|
| **FULL** | HeyGen | `HEYGEN_LIVE_AVATAR_API_KEY` |
| **Pipecat (clínico)** | ominis-2.0-clinic | `PIPECAT_AGENT_NAME` + `PIPECAT_API_TOKEN` |

When Pipecat is configured, the session endpoint prefers it and returns a Daily room. Otherwise uses HeyGen FULL.

## Backend Endpoint

`POST /v1/liveavatar/chat/completions` accepts OpenAI chat format:

```json
{
  "messages": [
    {"role": "system", "content": "Eres un asistente médico..."},
    {"role": "user", "content": "¿Qué es la diabetes tipo 2?"}
  ],
  "stream": true
}
```

Returns OpenAI-style SSE stream: `data: {"choices":[{"delta":{"content":"..."}}]}\n\n`

Always uses `ominis-2.0-clinic` with RAG, web search, PubMed, and clinical validation.

## Environment (Backend)

| Variable | Description |
|----------|-------------|
| `LIVEAVATAR_QUERY_URL` | Base URL for internal self-calls (e.g. `http://localhost:8000`). Use when the backend cannot reach itself via `request.base_url` (e.g. behind proxy). |

## Demo (Pipecat)

See `liveavatar-demo/` for the full Pipecat script. Requires:

- Ominis backend running
- HEYGEN_LIVE_AVATAR_API_KEY
- DEEPGRAM_API_KEY (STT)
- CARTESIA_API_KEY (TTS)
- Daily or WebRTC transport

## API Key Auth

The endpoint is included in `API_KEY_PATHS`. Pass `X-API-Key` or `Authorization: Bearer <key>` when the backend requires it.
