#!/bin/bash
# Make Ollama start automatically on an existing Vast instance (Ominis 2.0).
# Vast "update instance" does not allow setting only --onstart, so we document the
# reliable method: run the crontab command below inside the instance (SSH or Connect).
# See: docs/VAST_OLLAMA_QWEN_VL.md (§ Make Ollama permanent)

set -e

echo "=== Make Ollama permanent on Vast instance (Ominis 2.0) ==="
echo ""
echo "From your SSH or Vast Connect shell on the instance, run:"
echo ""
echo "1. Install cron (if crontab: command not found):"
echo "   AlmaLinux/RHEL:  dnf install -y cronie && crond"
echo "   Debian/Ubuntu:   apt-get update && apt-get install -y cron && service cron start"
echo ""
echo "2. Add @reboot job:"
echo "   (crontab -l 2>/dev/null; echo '@reboot export OLLAMA_HOST=0.0.0.0 && nohup ollama serve >> /var/log/ollama.log 2>&1 &') | crontab -"
echo "   crontab -l   # verify"
echo ""
echo "After that, ollama serve will start automatically when the instance (re)boots."
echo "Your current ollama process can keep running; crontab only affects the next boot."
echo ""
echo "For new instances, use ./infrastructure/24f-vast-ai-create-ollama-qwen-vl.sh"
echo "which sets --onstart-cmd at creation time."
