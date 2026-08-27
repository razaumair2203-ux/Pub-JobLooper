"""Own the single local dashboard process without killing unrelated services."""
import json
import os
import secrets
import time
import urllib.error
import urllib.request

from . import store


DASHBOARD_VERSION = '1.1.0'
HEALTH_SCHEMA = 'joblooper.dashboard-health.v1'
CONTROL_SCHEMA = 'joblooper.dashboard-instance.v1'
CONTROL_FILE = 'dashboard_instance.json'


def control_path():
    return store.data_p('index', CONTROL_FILE)


def health_payload(server):
    return {
        '_schema': HEALTH_SCHEMA,
        'product': 'Joblooper',
        'version': DASHBOARD_VERSION,
        'pid': os.getpid(),
        'port': server.server_address[1],
        'instance_id': server.instance_id,
    }


def register(server):
    """Persist the minimum private control record needed for a safe restart."""
    record = {
        '_schema': CONTROL_SCHEMA,
        'product': 'Joblooper',
        'version': DASHBOARD_VERSION,
        'pid': os.getpid(),
        'port': server.server_address[1],
        'instance_id': server.instance_id,
        'shutdown_token': server.shutdown_token,
        'started_at': store.now(),
    }
    store.write_json(control_path(), record)
    return record


def unregister(instance_id):
    path = control_path()
    record = store.read_json(path, {}) or {}
    if record.get('instance_id') == instance_id:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


def _health(port, timeout=1.5):
    try:
        with urllib.request.urlopen(
                f'http://127.0.0.1:{int(port)}/api/health', timeout=timeout) as response:
            value = json.loads(response.read().decode('utf-8'))
    except (OSError, ValueError, urllib.error.URLError):
        return None
    return value if isinstance(value, dict) else None


def stop_registered(port, timeout=5):
    """Stop only the Joblooper instance authenticated by the private record.

    Returns True when a live registered instance was stopped and False when no
    live instance owns the requested port. A mismatched live service is never
    terminated.
    """
    port = int(port)
    if port == 0:
        return False
    path = control_path()
    record = store.read_json(path, {}) or {}
    if record.get('_schema') != CONTROL_SCHEMA or record.get('port') != port:
        return False
    health = _health(port)
    if not health:
        unregister(record.get('instance_id'))
        return False
    identity = ('_schema', 'product', 'pid', 'port', 'instance_id')
    expected = {
        '_schema': HEALTH_SCHEMA, 'product': 'Joblooper',
        **{key: record.get(key) for key in ('pid', 'port', 'instance_id')},
    }
    if any(health.get(key) != expected.get(key) for key in identity):
        raise RuntimeError(
            f'port {port} is live but does not match the registered Joblooper instance; '
            'nothing was terminated')
    request = urllib.request.Request(
        f'http://127.0.0.1:{port}/api/admin/shutdown', data=b'{}', method='POST',
        headers={
            'Content-Type': 'application/json',
            'X-Joblooper-Shutdown': str(record.get('shutdown_token') or ''),
        })
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            if response.status != 200:
                raise RuntimeError('registered dashboard refused the restart request')
    except urllib.error.HTTPError as error:
        raise RuntimeError(
            f'registered dashboard refused the restart request ({error.code})') from error
    deadline = time.monotonic() + max(0.5, float(timeout))
    while time.monotonic() < deadline:
        if _health(port, timeout=0.2) is None:
            return True
        time.sleep(0.05)
    raise RuntimeError(f'previous Joblooper dashboard did not release port {port}')


def configure_server(server):
    server.instance_id = secrets.token_urlsafe(18)
    server.shutdown_token = secrets.token_urlsafe(32)
    return server
