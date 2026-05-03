from pyngrok import ngrok
import subprocess
import time

# Start Flask app in background
subprocess.Popen(["python", "main.py"], shell=True)
time.sleep(3)  # Wait for server to start

# Create public tunnel
public_url = ngrok.connect(5000)
print(f"🌐 PUBLIC LINK: {public_url}")
print(f"📱 Share this link with anyone!")
print(f"🔗 Direct access: {public_url}/attendance")

# Keep tunnel alive
input("Press Enter to stop...")
