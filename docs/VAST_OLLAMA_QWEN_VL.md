# Vast.ai: Ollama Qwen3 + Qwen2.5-VL (chat + vision)

Single Vast.ai instance with **Ollama** serving:
- **Qwen3** (e.g. `qwen3:14b`) for general chat when there is **no image**.
- **Qwen2.5-VL** (e.g. `qwen2.5vl:7b`) when the user sends an **image** (vision).

One A100 40GB so both models can be loaded in VRAM.

## 1. Create the instance

```bash
./infrastructure/24f-vast-ai-create-ollama-qwen-vl.sh
```

Wait until the instance is **running** in the Vast dashboard.

New instances created with the script run **ollama serve** automatically on start (onstart script). If you had to run `ollama serve` manually, see **Make Ollama permanent (existing instance)** below.

## 2. Get IP and port

In Vast.ai → **Instances** → your instance → **IP & Port Info**: note the **external** host and port mapped to internal **11434** (e.g. `1.2.3.4:45678`).

## 3. Pull models (from any machine that can reach the instance)

**Option A – curl (if your network can reach the instance):**
```bash
curl -X POST http://<IP>:<PORT>/api/pull -d '{"name":"qwen3:14b"}'
curl -X POST http://<IP>:<PORT>/api/pull -d '{"name":"qwen2.5vl:7b"}'
```
Wait for each pull to finish before starting the next.

**Option B – via backend:** `./infrastructure/pull-ollama-qwen-vl-via-backend.sh`

**Option C – from Vast Connect (no SSH key needed):** In Vast dashboard → instance → **Connect** → open the in-browser terminal/shell. Then:
```bash
ollama pull qwen3:14b
ollama pull qwen2.5vl:7b
ollama list
```
If you see "Permission denied (publickey)" when using the **proxy SSH** command from "Terminal Connection Options", see **SSH: Permission denied** below.

## 4. Configure backend

Copy the example and set the URL:

```bash
cp config/ollama_qwen_vast.txt.example config/ollama_qwen_vast.txt
# Edit config/ollama_qwen_vast.txt: set OLLAMA_QWEN_VAST_URL=http://<IP>:<PORT>
```

Then update the Haystack backend env and restart:

```bash
./infrastructure/20c-vast-update-backend-env-ollama-qwen-vl.sh
```

The script reads `config/ollama_qwen_vast.txt` (or you can pass the URL as first argument). It sets `OLLAMA_URL`, `OLLAMA_MODEL`, and `VISION_MODEL` on the backend and restarts the service.

## Summary: three Vast setups

| Vast instance | Script | Backend update | Use |
|---------------|--------|----------------|-----|
| **Med42** | (already there) | `20b-vast-update-backend-env-med42.sh` | Clinical translator (Research mode) |
| **OpenScholar 128K** | `24e-vast-ai-create-openscholar-128k.sh` | `20a-vast-update-backend-env-openscholar-128k.sh` | Long synthesis (Research), A100 |
| **Ollama Qwen + VL** | `24f-vast-ai-create-ollama-qwen-vl.sh` | `20c-vast-update-backend-env-ollama-qwen-vl.sh` | General chat + vision |

See also: [VAST_DEPLOY_AND_EC2_CLEANUP.md](VAST_DEPLOY_AND_EC2_CLEANUP.md).

---

## Make Ollama permanent (existing instance)

If you created the instance **before** the script had the onstart (or had to run `ollama serve` manually once), make it start on every boot.

**From the instance** (SSH or Vast **Connect** → in-browser shell):

1. **Install cron** (the `ollama/ollama` image often has no crontab by default):
   - **AlmaLinux/RHEL** (official Ollama image):
     ```bash
     dnf install -y cronie && crond
     ```
   - **Debian/Ubuntu** (if your image is Debian-based):
     ```bash
     apt-get update && apt-get install -y cron && service cron start
     ```

2. **Add the @reboot job:**
   ```bash
   (crontab -l 2>/dev/null; echo '@reboot export OLLAMA_HOST=0.0.0.0 && nohup ollama serve >> /var/log/ollama.log 2>&1 &') | crontab -
   crontab -l   # verify
   ```

After that, `ollama serve` will run automatically when the instance (re)boots. You can leave the current `ollama serve` running; the crontab only affects the next boot.

**Helper (prints the command):** `./infrastructure/24g-vast-ai-set-ollama-onstart.sh`  
**New instances:** use `24f-vast-ai-create-ollama-qwen-vl.sh`; it sets `--onstart-cmd` at creation so no crontab is needed.

---

## SSH: Permission denied (publickey)

If the proxy SSH command from Vast’s **Terminal Connection Options** fails with `Permission denied (publickey)`:

1. **Use the in-browser Connect instead**  
   Click **Connect** on the instance and use the web terminal. No SSH key is required. You can run `ollama serve`, `ollama list`, and the crontab there.

2. **To fix SSH from your machine**  
   - Add your **public** key to Vast: [Account → Keys](https://cloud.vast.ai/account/) (or `vastai create ssh-key` after pasting the key).  
   - For **existing** instances, attach the key: in the instance card use “SSH Keys” / “Attach” or see [Vast SSH docs](https://docs.vast.ai/documentation/instances/connect/ssh).  
   - Use the key explicitly: `ssh -i ~/.ssh/id_ed25519 -p <PORT> root@ssh8.vast.ai -L 11434:localhost:11434` (replace `<PORT>` with the proxy port from the instance’s Terminal Connection Options).  
   - Key changes can take 1–2 minutes to apply. Ensure the key file has correct permissions (`chmod 600 ~/.ssh/id_ed25519`).
