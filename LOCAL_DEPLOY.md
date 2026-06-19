# Local Deployment (while your PC is running)

This lets you run the Elliott Wave Scanner on **your own computer** and make the results publicly viewable via a tunnel (like ngrok).

While your PC + the server + tunnel is running, other people can visit the public URL, see the latest scan, and even click "Run Scan Now" to trigger a fresh scan on your machine.

## Quick Start (Windows)

1. **Install Flask** (one time)
   ```bash
   pip install flask
   ```

2. **Run the local server**
   Open PowerShell or CMD in the `elliott-wave-scanner` folder:
   ```bash
   python local_server.py
   ```
   You should see: "Starting local Elliott Wave Scanner web server..."
   Keep this window open.

3. **Expose it to the internet with ngrok** (free)
   - Go to https://ngrok.com and create a free account + download ngrok.
   - Unzip and add to PATH, or just run from the folder.
   - Authenticate once:
     ```bash
     ngrok config add-authtoken YOUR_TOKEN_HERE
     ```
   - Start the tunnel (in a **new** terminal):
     ```bash
     ngrok http 5000
     ```
   - Copy the **https** URL it gives you (e.g. https://abc123.ngrok-free.app)

4. **Share the URL**
   Anyone who visits that ngrok URL while your server + ngrok are running will see the live results page.

5. **Run a scan from the web**
   On the website there is a big green "Run Scan Now" button.
   Clicking it will execute the scanner on **your computer** and update the results for everyone.

## How to stop
- Close the `local_server.py` terminal.
- Close the ngrok terminal.
- The public URL will stop working until you start them again.

## Tips
- Keep both terminals running in the background if you want constant availability.
- You can make a simple .bat file:
  ```bat
  start cmd /k "ngrok http 5000"
  python local_server.py
  ```
- For even better uptime, consider a cheap VPS or always-on mini PC + cloudflared (Cloudflare Tunnel, no port forwarding needed).
- The scan uses your real IP, so Binance access works normally (unlike GitHub Actions).

## Files involved
- `local_server.py` — the web server + API
- `results/latest.json` — the data the page reads
- Your existing `elliott_wave_scanner.py` — the actual scanner (called by the server when you click Run)

That's it! Much simpler than GitHub Actions for personal use, and it respects that your machine can reach Binance. 

If you want a version with basic password protection or auto-start on boot, let me know.