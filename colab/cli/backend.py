"""Read runtime metadata through the official Colab client."""
import base64
from pathlib import Path
from urllib.parse import quote

from colab.cli.settings import CONFIG, account_directory, session_file


class AccountError(RuntimeError):
    """Describe an account failure without credential data."""


def credentials(worker_id):
    """Load and refresh one account without global environment changes."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    path = account_directory(worker_id) / "credentials.json"
    if not path.is_file():
        raise AccountError("auth_required")
    result = Credentials.from_authorized_user_file(str(path))
    if not result.valid:
        transport = Request()
        def bounded_request(*args, **kwargs):
            kwargs["timeout"] = CONFIG["request_timeout"]
            return transport(*args, **kwargs)
        result.refresh(bounded_request)
    return result


def client(worker_id):
    """Create a separate HTTP session for each account."""
    from colab_cli.client import Client, Prod
    from google.auth.transport.requests import AuthorizedSession

    class BoundedSession(AuthorizedSession):
        def request(self, method, url, **kwargs):
            kwargs.setdefault("timeout", CONFIG["request_timeout"])
            return super().request(method, url, **kwargs)

    return Client(Prod(), BoundedSession(credentials(worker_id), refresh_timeout=CONFIG["request_timeout"]))


def proxy_request(assignment, method, path, **kwargs):
    """Use a short-lived runtime token without logs of request secrets."""
    import requests
    proxy = assignment.runtime_proxy_info
    response = requests.request(method, proxy.url.rstrip("/") + path,
        params={"colab-runtime-proxy-token": proxy.token},
        headers={"X-Colab-Runtime-Proxy-Token": proxy.token},
        timeout=CONFIG["request_timeout"], **kwargs)
    response.raise_for_status()
    return response.json() if response.content else None


def contents(assignment, path, content=True):
    """Read one directory or file without kernel execution."""
    suffix = "?content=1" if content else "?content=0"
    # The token remains in the request parameters, separate from the path.
    return proxy_request(assignment, "GET", "/api/contents/" + quote(path.strip("/"), safe="/") + suffix)


def attach(worker_id, endpoint=None):
    """Register an existing VM without allocation or kernel changes."""
    from colab_cli.state import SessionState, StateStore
    assignments = client(worker_id).list_assignments()
    selected = [a for a in assignments if not endpoint or a.endpoint == endpoint]
    if len(selected) != 1:
        raise AccountError("Specify one endpoint when the account has zero or multiple runtimes.")
    assignment = selected[0]
    store = StateStore(str(session_file(worker_id)))
    name = f"zq-worker-{worker_id}"
    previous = store.get(name)
    proxy = assignment.runtime_proxy_info
    state = SessionState(name=name, token=proxy.token, url=proxy.url, endpoint=assignment.endpoint,
        variant=assignment.variant.name, accelerator=assignment.accelerator.value)
    if previous and previous.endpoint == state.endpoint:
        state.kernel_id, state.session_id = previous.kernel_id, previous.session_id
        state.keep_alive_pid = previous.keep_alive_pid
    store.add(state)
    return assignment.endpoint


def decode_text(model):
    """Decode a small text artifact from the contents API."""
    value = model.get("content", "")
    if model.get("format") == "base64":
        return base64.b64decode(value).decode("utf-8")
    return str(value)


def error_status(error):
    """Classify failures without response bodies or request URLs."""
    from google.auth.exceptions import RefreshError
    status = getattr(getattr(error, "response", None), "status_code", None)
    if isinstance(error, RefreshError) or status in (401, 403) or str(error) == "auth_required":
        return "auth_required"
    return "unreachable"
