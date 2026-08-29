"""Optional real-Chrome smoke for the applicant's capture-to-review journey."""
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, 'examples', 'starter')
sys.path.insert(0, ROOT)

from core import dashboard, store, vec


class QuietBridge:
    def status(self):
        return {
            'available': False, 'connected': False, 'active_tasks': 0,
            'error': None, 'integration': 'browser-smoke',
            'approval_mode': 'user',
        }

    def close(self):
        pass


def _chrome():
    candidates = [
        shutil.which('google-chrome'), shutil.which('google-chrome-stable'),
        shutil.which('chromium'), shutil.which('chromium-browser'),
        os.path.join(os.environ.get('ProgramFiles', ''),
                     'Google', 'Chrome', 'Application', 'chrome.exe'),
        os.path.join(os.environ.get('ProgramFiles(x86)', ''),
                     'Microsoft', 'Edge', 'Application', 'msedge.exe'),
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    ]
    return next((path for path in candidates if path and os.path.isfile(path)), None)


def main():
    chrome = _chrome()
    node = shutil.which('node')
    if not chrome or not node:
        print('  skip real-browser journey (Chrome/Edge and Node are optional test tools)')
        return 0

    with tempfile.TemporaryDirectory(prefix='joblooper-browser-') as root:
        data = os.path.join(root, 'data')
        profile = os.path.join(root, 'chrome-profile')
        shutil.copytree(FIXTURE, data)
        store.configure(data)
        vec.reset_caches()
        server = dashboard.create_server(0, quiet=True, bridge=QuietBridge())
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        dashboard_port = server.server_address[1]
        flags = 0
        if os.name == 'nt':
            flags = subprocess.CREATE_NO_WINDOW
        browser = subprocess.Popen([
            chrome, '--headless=new', '--disable-gpu', '--no-first-run',
            '--no-default-browser-check', '--no-sandbox',
            '--remote-debugging-port=0', f'--user-data-dir={profile}',
            f'http://127.0.0.1:{dashboard_port}/',
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
           creationflags=flags)
        try:
            active_port = os.path.join(profile, 'DevToolsActivePort')
            deadline = time.time() + 20
            while time.time() < deadline and not os.path.isfile(active_port):
                if browser.poll() is not None:
                    raise RuntimeError('headless browser exited before opening the dashboard')
                time.sleep(0.1)
            if not os.path.isfile(active_port):
                raise RuntimeError('headless browser did not publish a DevTools port')
            with open(active_port, encoding='utf-8') as stream:
                debug_port = stream.readline().strip()
            result = subprocess.run([
                node, os.path.join(ROOT, 'tests', 'browser_dashboard_smoke.js'),
                debug_port, str(dashboard_port),
            ], cwd=ROOT, text=True, stdout=subprocess.PIPE,
               stderr=subprocess.STDOUT, timeout=240)
            print(result.stdout.rstrip())
            return result.returncode
        finally:
            browser.terminate()
            try:
                browser.wait(timeout=10)
            except subprocess.TimeoutExpired:
                browser.kill()
                browser.wait(timeout=10)
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    raise SystemExit(main())
