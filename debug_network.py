import socket
import sys
import subprocess
import urllib.request
import urllib.error
import time

def log(msg):
    print(msg)
    sys.stdout.flush()

def check_ip():
    log("\n--- 1. PUBLIC IP CHECK ---")
    try:
        with urllib.request.urlopen('https://api.ipify.org', timeout=5) as response:
            ip = response.read().decode('utf8')
            log(f"✅ Public IP: {ip}")
    except Exception as e:
        log(f"❌ Failed to get Public IP: {e}")

def check_dns(host):
    log(f"\n--- 2. DNS LOOKUP: {host} ---")
    try:
        ip = socket.gethostbyname(host)
        log(f"✅ Resolved {host} -> {ip}")
        return ip
    except Exception as e:
        log(f"❌ DNS Resolution Failed: {e}")
        return None

def tcp_ping(host, port, name):
    log(f"\n--- 3. TCP PING: {name} ({host}:{port}) ---")
    try:
        sock = socket.create_connection((host, port), timeout=5)
        sock.close()
        log(f"✅ Connected to {host}:{port}")
    except socket.timeout:
        log(f"❌ TIMEOUT connecting to {host}:{port}")
    except OSError as e:
        log(f"❌ FAILED connecting to {host}:{port}: {e}")

def check_http(url):
    log(f"\n--- 4. HTTP REQUEST: {url} ---")
    try:
        # Use a real User-Agent to avoid 403s from some WAFs (though Telegram API usually fine)
        req = urllib.request.Request(
            url, 
            data=None, 
            headers={'User-Agent': 'WebDog-Diagnostic/1.0'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            log(f"✅ HTTP {response.status}: {response.reason}")
    except urllib.error.HTTPError as e:
        # 4xx/5xx are technically "connectivity success" even if application error
        log(f"⚠️ HTTP Error {e.code}: {e.reason} (Connectivity OK)")
    except urllib.error.URLError as e:
        log(f"❌ URL Error: {e.reason}")
    except Exception as e:
        log(f"❌ Request Failed: {e}")

def check_mtu():
    log("\n--- 5. INTERFACE CONFIG (MTU) ---")
    try:
        # Try 'ip addr' first, fall back to 'ifconfig'
        result = subprocess.run(['ip', 'addr'], capture_output=True, text=True)
        if result.returncode == 0:
            log(result.stdout)
        else:
            result = subprocess.run(['ifconfig'], capture_output=True, text=True)
            log(result.stdout)
    except FileNotFoundError:
        log("⚠️ Could not run 'ip addr' or 'ifconfig' (Command not found)")
    except Exception as e:
        log(f"❌ Failed to check interfaces: {e}")

if __name__ == "__main__":
    log("🚀 STARTING WEBDOG NETWORK DIAGNOSTIC")
    log(f"Time: {time.ctime()}")
    
    check_ip()
    
    tg_ip = check_dns("api.telegram.org")
    
    tcp_ping("8.8.8.8", 53, "Google DNS (Raw Internet)")
    
    if tg_ip:
        tcp_ping(tg_ip, 443, "Telegram API (Resolved IP)")
    else:
        log("⚠️ Skipping Telegram TCP Ping due to DNS failure.")
        
    # Also ping the Hardcoded IP to see if the block is definitely not IP-based
    tcp_ping("149.154.167.220", 443, "Telegram API (Hardcoded IP)")
    
    check_http("https://api.telegram.org")
    
    check_mtu()
    
    log("\n✅ DIAGNOSTIC COMPLETE")
