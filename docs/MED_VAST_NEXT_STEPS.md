# Ominis 2.0 Med on Vast — Next steps

A Vast Ollama instance for Med was created (contract **31897424**). To use it:

## 1. Get the Ollama URL (IP + external port)

- Open [Vast.ai Instances](https://cloud.vast.ai/instances/).
- Find instance **31897424** (or the one created by `24d-vast-ai-create-ollama-med.sh`).
- Click **IP Port Info**.
- Find the line that maps to **11434/tcp**, it should be `50.217.254.161:41598 -> 11434/tcp`.
- Your Ollama base URL is: `http://50.217.254.161:41598`.

## 2. Pull Med42 on that instance

```bash
./infrastructure/pull-med42-via-api.sh http://50.217.254.161:41598
```

Wait until the pull finishes (first time can take several minutes). You can check: `curl -s http://50.217.254.161:41598/api/tags`.

## 3. Point the backend to Vast for Med

Edit `config/ollama_med_server.txt`:

```bash
OLLAMA_MED_MODEL=hf.co/SandLogicTechnologies/Llama3-Med42-8B-GGUF
OLLAMA_MED_URL=http://50.217.254.161:41598
OLLAMA_MED_INSTANCE_ID=
```

Then:

```bash
./infrastructure/20med-update-backend-env-ollama-med.sh
```

## 4. Use Ominis 2.0 Med in the chat

In https://ia.ominis.org choose **Ominis 2.0 Med** and send a message. Responses will be served from the Vast Ollama instance (faster than g4dn).

---

**Alternative (Med on g4dn):** If you prefer to run Med on the existing Ollama server (3.213.91.241) instead of Vast, run from a machine that can SSH to that host:

```bash
./infrastructure/install-med42-on-ollama.sh
```

Leave `OLLAMA_MED_URL` empty in `config/ollama_med_server.txt` and run `20med-update-backend-env-ollama-med.sh`. Med will use the same server as Ominis 2.0.
