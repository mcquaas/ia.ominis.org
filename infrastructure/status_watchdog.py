#!/usr/bin/env python3
"""
OMINIS Health Status Watchdog
Monitors all services and generates an HTML status page.
"""
import json
import urllib.request
import urllib.error
import socket
import time
import os
from datetime import datetime, timezone

# Configuration
# Monitors only resources that matter for the working system.
# LLM check uses Haystack's /system-stats/health (same path as actual inference).
SERVICES = {
    "frontend": {
        "name": "Frontend (ia.ominis.org)",
        "url": "https://ia.ominis.org",
        "type": "http",
        "timeout": 10,
        "critical": True
    },
    "haystack_api": {
        "name": "Agent API (api.ominis.org)",
        "url": "http://127.0.0.1:8000/v1/health",
        "display_url": "api.ominis.org",
        "type": "json",
        "expected_key": "status",
        "timeout": 10,
        "critical": True
    },
    "llm_inference": {
        "name": "LLM Inference",
        "url": "http://127.0.0.1:8000/v1/system-stats/health",
        "display_url": "api.ominis.org",
        "type": "health_status",
        "expected_value": "healthy",
        "timeout": 15,
        "critical": True
    }
}

STATUS_FILE = "/var/www/status/index.html"
STATUS_JSON = "/var/www/status/status.json"
HISTORY_FILE = "/var/www/status/history.json"
MAX_HISTORY = 100  # Keep last 100 status changes

def check_http(url, timeout):
    """Check if HTTP endpoint responds with 2xx status."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'OMINIS-Watchdog/1.0'})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status >= 200 and response.status < 400, f"HTTP {response.status}", None
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}", str(e)
    except urllib.error.URLError as e:
        return False, "Connection failed", str(e.reason)
    except socket.timeout:
        return False, "Timeout", f"No response within {timeout}s"
    except Exception as e:
        return False, "Error", str(e)

def check_json(url, expected_key, timeout):
    """Check if JSON endpoint responds with expected key."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'OMINIS-Watchdog/1.0'})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode('utf-8'))
            if expected_key in data:
                return True, "OK", None
            return False, "Invalid response", f"Missing key: {expected_key}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}", str(e)
    except urllib.error.URLError as e:
        return False, "Connection failed", str(e.reason)
    except socket.timeout:
        return False, "Timeout", f"No response within {timeout}s"
    except json.JSONDecodeError as e:
        return False, "Invalid JSON", str(e)
    except Exception as e:
        return False, "Error", str(e)


def check_health_status(url, expected_value, timeout):
    """Check if health endpoint returns expected status (e.g. 'healthy')."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'OMINIS-Watchdog/1.0'})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode('utf-8'))
            status = data.get("status", "")
            if status == expected_value:
                return True, "Online", None
            return False, f"Status: {status}", f"Expected '{expected_value}', got '{status}'"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}", str(e)
    except urllib.error.URLError as e:
        return False, "Connection failed", str(e.reason)
    except socket.timeout:
        return False, "Timeout", f"No response within {timeout}s"
    except json.JSONDecodeError as e:
        return False, "Invalid JSON", str(e)
    except Exception as e:
        return False, "Error", str(e)

def check_model(url, model_name, timeout):
    """Check if a specific model is available in Ollama."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'OMINIS-Watchdog/1.0'})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode('utf-8'))
            models = data.get('models', [])
            for model in models:
                if model.get('name') == model_name:
                    size_gb = model.get('size', 0) / (1024**3)
                    return True, f"Loaded ({size_gb:.1f}GB)", None
            return False, "Not loaded", f"Model {model_name} not found"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}", str(e)
    except urllib.error.URLError as e:
        return False, "Connection failed", str(e.reason)
    except socket.timeout:
        return False, "Timeout", f"No response within {timeout}s"
    except Exception as e:
        return False, "Error", str(e)

def check_service(service_id, config):
    """Check a single service and return status."""
    start_time = time.time()
    
    check_type = config.get('type', 'http')
    url = config['url']
    timeout = config.get('timeout', 10)
    
    if check_type == 'http':
        ok, status, error = check_http(url, timeout)
    elif check_type == 'json':
        ok, status, error = check_json(url, config.get('expected_key', 'status'), timeout)
    elif check_type == 'health_status':
        ok, status, error = check_health_status(
            url, config.get('expected_value', 'healthy'), timeout
        )
    elif check_type == 'model_check':
        ok, status, error = check_model(url, config.get('model_name'), timeout)
    else:
        ok, status, error = False, "Unknown type", f"Unknown check type: {check_type}"
    
    response_time = round((time.time() - start_time) * 1000)  # ms
    
    # Use display_url if provided, otherwise derive from url
    display_url = config.get('display_url')
    if not display_url:
        display_url = url if not url.startswith('http://127') else "(internal)"
    
    return {
        "id": service_id,
        "name": config['name'],
        "ok": ok,
        "status": status,
        "error": error,
        "response_time_ms": response_time,
        "critical": config.get('critical', False),
        "url": display_url
    }

def load_history():
    """Load status history from file."""
    try:
        with open(HISTORY_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

def save_history(history):
    """Save status history to file."""
    try:
        os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
        with open(HISTORY_FILE, 'w') as f:
            json.dump(history[-MAX_HISTORY:], f, indent=2)
    except Exception as e:
        print(f"Error saving history: {e}")

def record_changes(results, history):
    """Record status changes to history."""
    now = datetime.now(timezone.utc).isoformat()
    
    # Build current status map
    current = {r['id']: r['ok'] for r in results}
    
    # Get previous status map
    previous = {}
    if history:
        last_entry = history[-1]
        previous = {s['id']: s['ok'] for s in last_entry.get('services', [])}
    
    # Find changes
    changes = []
    for service_id, is_ok in current.items():
        prev_ok = previous.get(service_id)
        if prev_ok is None or prev_ok != is_ok:
            service_name = next((r['name'] for r in results if r['id'] == service_id), service_id)
            changes.append({
                "service": service_name,
                "from": "up" if prev_ok else ("down" if prev_ok is False else "unknown"),
                "to": "up" if is_ok else "down",
                "time": now
            })
    
    # Add to history if there are changes or it's the first entry
    if changes or not history:
        history.append({
            "timestamp": now,
            "services": results,
            "changes": changes
        })
    
    return changes

def generate_html(results, last_check, history):
    """Generate HTML status page."""
    all_ok = all(r['ok'] for r in results if r['critical'])
    overall_status = "Operational" if all_ok else "Degraded"
    overall_class = "status-ok" if all_ok else "status-error"
    
    # Get recent changes (last 10)
    recent_changes = []
    for entry in reversed(history[-20:]):
        for change in entry.get('changes', []):
            recent_changes.append(change)
            if len(recent_changes) >= 10:
                break
        if len(recent_changes) >= 10:
            break
    
    services_html = ""
    for r in results:
        status_class = "status-ok" if r['ok'] else "status-error"
        status_icon = "✓" if r['ok'] else "✗"
        error_html = f'<div class="error-detail">{r["error"]}</div>' if r.get('error') else ''
        critical_badge = '<span class="badge critical">Core</span>' if r['critical'] else ''
        
        services_html += f'''
        <div class="service-card {status_class}">
            <div class="service-header">
                <span class="status-icon">{status_icon}</span>
                <span class="service-name">{r['name']}</span>
                {critical_badge}
            </div>
            <div class="service-details">
                <span class="status-text">{r['status']}</span>
                <span class="response-time">{r['response_time_ms']}ms</span>
            </div>
            {error_html}
        </div>
        '''
    
    changes_html = ""
    if recent_changes:
        for change in recent_changes:
            change_class = "change-up" if change['to'] == 'up' else "change-down"
            arrow = "↑" if change['to'] == 'up' else "↓"
            time_str = change['time'][:19].replace('T', ' ')
            changes_html += f'''
            <div class="change-item {change_class}">
                <span class="change-arrow">{arrow}</span>
                <span class="change-service">{change['service']}</span>
                <span class="change-time">{time_str} UTC</span>
            </div>
            '''
    else:
        changes_html = '<div class="no-changes">No recent changes</div>'
    
    html = f'''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="60">
    <title>OMINIS Status</title>
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🏥</text></svg>">
    <style>
        :root {{
            --bg-dark: #0a1628;
            --bg-card: #1a2744;
            --text-primary: #ffffff;
            --text-secondary: #8892a6;
            --accent-green: #10b981;
            --accent-red: #ef4444;
            --accent-yellow: #f59e0b;
            --accent-blue: #3b82f6;
        }}
        
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: var(--bg-dark);
            color: var(--text-primary);
            min-height: 100vh;
            padding: 2rem;
        }}
        
        .container {{
            max-width: 900px;
            margin: 0 auto;
        }}
        
        header {{
            text-align: center;
            margin-bottom: 2rem;
        }}
        
        .logo {{
            font-size: 2rem;
            font-weight: 700;
            color: var(--accent-blue);
            margin-bottom: 0.5rem;
        }}
        
        .overall-status {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.75rem 1.5rem;
            border-radius: 2rem;
            font-size: 1.1rem;
            font-weight: 600;
            margin: 1rem 0;
        }}
        
        .overall-status.status-ok {{
            background: rgba(16, 185, 129, 0.2);
            color: var(--accent-green);
            border: 1px solid var(--accent-green);
        }}
        
        .overall-status.status-error {{
            background: rgba(239, 68, 68, 0.2);
            color: var(--accent-red);
            border: 1px solid var(--accent-red);
        }}
        
        .last-check {{
            color: var(--text-secondary);
            font-size: 0.9rem;
        }}
        
        .section-title {{
            font-size: 1.2rem;
            color: var(--text-secondary);
            margin: 2rem 0 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        
        .services-grid {{
            display: grid;
            gap: 1rem;
        }}
        
        .service-card {{
            background: var(--bg-card);
            border-radius: 0.75rem;
            padding: 1rem 1.25rem;
            border-left: 4px solid;
        }}
        
        .service-card.status-ok {{
            border-left-color: var(--accent-green);
        }}
        
        .service-card.status-error {{
            border-left-color: var(--accent-red);
        }}
        
        .service-header {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
            margin-bottom: 0.5rem;
        }}
        
        .status-icon {{
            font-size: 1.2rem;
        }}
        
        .status-ok .status-icon {{ color: var(--accent-green); }}
        .status-error .status-icon {{ color: var(--accent-red); }}
        
        .service-name {{
            font-weight: 600;
            flex: 1;
        }}
        
        .badge {{
            font-size: 0.7rem;
            padding: 0.2rem 0.5rem;
            border-radius: 0.25rem;
            text-transform: uppercase;
            font-weight: 600;
        }}
        
        .badge.critical {{
            background: rgba(239, 68, 68, 0.2);
            color: var(--accent-red);
        }}
        
        .service-details {{
            display: flex;
            justify-content: space-between;
            color: var(--text-secondary);
            font-size: 0.9rem;
        }}
        
        .response-time {{
            font-family: monospace;
        }}
        
        .error-detail {{
            margin-top: 0.5rem;
            padding: 0.5rem;
            background: rgba(239, 68, 68, 0.1);
            border-radius: 0.25rem;
            font-size: 0.85rem;
            color: var(--accent-red);
        }}
        
        .changes-list {{
            background: var(--bg-card);
            border-radius: 0.75rem;
            padding: 1rem;
        }}
        
        .change-item {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.5rem 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }}
        
        .change-item:last-child {{ border-bottom: none; }}
        
        .change-arrow {{
            font-size: 1.2rem;
            width: 1.5rem;
            text-align: center;
        }}
        
        .change-up .change-arrow {{ color: var(--accent-green); }}
        .change-down .change-arrow {{ color: var(--accent-red); }}
        
        .change-service {{
            flex: 1;
            font-weight: 500;
        }}
        
        .change-time {{
            color: var(--text-secondary);
            font-size: 0.85rem;
            font-family: monospace;
        }}
        
        .no-changes {{
            color: var(--text-secondary);
            text-align: center;
            padding: 1rem;
        }}
        
        footer {{
            text-align: center;
            margin-top: 3rem;
            color: var(--text-secondary);
            font-size: 0.85rem;
        }}
        
        footer a {{
            color: var(--accent-blue);
            text-decoration: none;
        }}
        
        @media (max-width: 600px) {{
            body {{ padding: 1rem; }}
            .service-details {{ flex-direction: column; gap: 0.25rem; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="logo">OMINIS Status</div>
            <div class="overall-status {overall_class}">
                <span>{"✓" if all_ok else "⚠"}</span>
                <span>{overall_status}</span>
            </div>
            <div class="last-check">Last check: {last_check} UTC</div>
        </header>
        
        <section>
            <h2 class="section-title">Services</h2>
            <div class="services-grid">
                {services_html}
            </div>
        </section>
        
        <section>
            <h2 class="section-title">Recent Changes</h2>
            <div class="changes-list">
                {changes_html}
            </div>
        </section>
        
        <footer>
            <p>Auto-refreshes every 60 seconds</p>
            <p style="margin-top: 0.5rem;">
                <a href="status.json">JSON API</a> · 
                <a href="https://ia.ominis.org">OMINIS AI</a>
            </p>
        </footer>
    </div>
</body>
</html>
'''
    return html

def main():
    """Main watchdog function."""
    print(f"[{datetime.now().isoformat()}] Starting status check...")
    
    # Check all services
    results = []
    for service_id, config in SERVICES.items():
        result = check_service(service_id, config)
        results.append(result)
        status_emoji = "✓" if result['ok'] else "✗"
        print(f"  {status_emoji} {result['name']}: {result['status']} ({result['response_time_ms']}ms)")
    
    # Load history and record changes
    history = load_history()
    changes = record_changes(results, history)
    
    if changes:
        print(f"  Changes detected: {len(changes)}")
        for change in changes:
            print(f"    - {change['service']}: {change['from']} → {change['to']}")
    
    save_history(history)
    
    # Generate outputs
    last_check = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
    
    # Write HTML
    html = generate_html(results, last_check, history)
    with open(STATUS_FILE, 'w') as f:
        f.write(html)
    
    # Write JSON
    json_data = {
        "timestamp": last_check,
        "overall": "operational" if all(r['ok'] for r in results if r['critical']) else "degraded",
        "services": results
    }
    with open(STATUS_JSON, 'w') as f:
        json.dump(json_data, f, indent=2)
    
    print(f"  Status page updated: {STATUS_FILE}")
    
    # Return exit code based on critical services
    critical_ok = all(r['ok'] for r in results if r['critical'])
    return 0 if critical_ok else 1

if __name__ == "__main__":
    exit(main())
