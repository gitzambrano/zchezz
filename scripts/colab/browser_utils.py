"""Browser session utilities and safe Playwright helpers for Colab automation in Zchezz.

Provides CDP connection fallback, profile lock detection, modal handling,
DOM state inspection, and safe cell execution primitives without terminating
active Chrome processes.
"""

import json
import os
import socket
import time
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
import psutil

# Anti-bot stealth initialization script
STEALTH_JS = """
if (navigator.webdriver) {
    try {
        Object.defineProperty(Object.getPrototypeOf(navigator), 'webdriver', {
            get: () => undefined,
            configurable: true
        });
    } catch (e) {}
}
if (!window.chrome) {
    window.chrome = { runtime: {} };
}
"""
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"


def save_profile_cookies(ctx: Any, profile_dir: str) -> None:
    """Save persistent cookies backup to cookies.json inside profile and project directory."""
    try:
        cookies = ctx.cookies()
        if not cookies:
            return

        # 1. Primary save inside profile directory
        out_path = Path(profile_dir) / "cookies.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)

        # 2. Local mirror inside the project repository (gitignored)
        mirror_dir = Path(__file__).resolve().parent / "cookies"
        mirror_dir.mkdir(parents=True, exist_ok=True)
        profile_name = Path(profile_dir).name
        mirror_path = mirror_dir / f"{profile_name}_cookies.json"
        with open(mirror_path, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)
    except Exception:
        pass


def load_profile_cookies(ctx: Any, profile_dir: str) -> None:
    """Load and inject persistent cookies backup from profile or local project mirror."""
    try:
        candidates = [
            Path(profile_dir) / "cookies.json",
            Path(__file__).resolve().parent / "cookies" / f"{Path(profile_dir).name}_cookies.json",
        ]
        for in_path in candidates:
            if in_path.is_file():
                with open(in_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                if saved:
                    ctx.add_cookies(saved)
                    return
    except Exception:
        pass


def launch_stealth_context(
    p: Any,
    profile_dir: str,
    headless: bool = True,
    cdp_port: Optional[int] = None,
    extra_args: Optional[List[str]] = None,
) -> Any:
    """Launch persistent Chrome context equipped with anti-bot detection and stealth flags."""
    args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-infobars",
        "--disable-dev-shm-usage",
        "--lang=pt-BR,pt,en-US,en",
    ]
    if cdp_port:
        args.append(f"--remote-debugging-port={cdp_port}")
        args.append("--remote-allow-origins=*")
    if extra_args:
        args.extend(extra_args)

    ctx = p.chromium.launch_persistent_context(
        user_data_dir=profile_dir,
        headless=headless,
        channel="chrome",
        user_agent=DEFAULT_USER_AGENT,
        viewport={"width": 1366, "height": 768},
        args=args,
        ignore_default_args=["--enable-automation"],
    )
    ctx.add_init_script(STEALTH_JS)
    load_profile_cookies(ctx, profile_dir)
    return ctx


def is_cdp_reachable(port: int, host: str = "127.0.0.1", timeout: float = 1.0) -> bool:
    """Check whether a Chrome DevTools Protocol port is open and accepting connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def is_profile_in_use(profile_dir: str) -> Tuple[bool, Optional[int]]:
    """Check if any running chrome.exe process is currently using the specified user data directory."""
    norm_target = os.path.normcase(os.path.abspath(profile_dir))
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            p_name = proc.info.get("name") or ""
            if "chrome" in p_name.lower():
                cmdline = proc.info.get("cmdline") or []
                cmd_str = " ".join(cmdline)
                norm_cmd = os.path.normcase(cmd_str)
                if norm_target in norm_cmd:
                    return True, proc.info.get("pid")
                for arg in cmdline:
                    if arg.startswith("--user-data-dir="):
                        val = os.path.normcase(os.path.abspath(arg.split("=", 1)[1].strip('"\'')))
                        if val == norm_target:
                            return True, proc.info.get("pid")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False, None


def dismiss_modals(page: Any) -> bool:
    """Detect and click common Colab warning, OAuth authorization, and confirmation dialogs."""
    try:
        return page.evaluate("""() => {
            const buttons = Array.from(document.querySelectorAll(
                'button, md-text-button, paper-button, .colab-dialog-button, colab-dialog button'
            ));
            const targets = [
                'Executar mesmo assim',
                'Executar de qualquer maneira',
                'Run anyway',
                'Conectar ao Google Drive',
                'Connect to Google Drive',
                'Continuar',
                'Continue',
                'OK',
                'Ok'
            ];
            for (const b of buttons) {
                const txt = (b.innerText || '').trim();
                for (const t of targets) {
                    if (txt === t || txt.includes(t)) {
                        b.click();
                        return true;
                    }
                }
            }
            return false;
        }""")
    except Exception:
        return False


def handle_google_oauth_popup(popup: Any, target_account: Optional[str] = None) -> bool:
    """Handle Google OAuth consent dialog popup for Google Drive connection."""
    try:
        if popup.is_closed():
            return False
        url = popup.url or ""
        if "accounts.google.com" not in url:
            return False

        # 1. Select account if account chooser is displayed
        if target_account:
            try:
                acc_loc = popup.locator(f"text={target_account}")
                if acc_loc.count() > 0 and acc_loc.first.is_visible():
                    acc_loc.first.click()
                    time.sleep(1)
            except Exception:
                pass

        # 2. Check checkboxes and click Continuar/Permitir
        for _ in range(4):
            if popup.is_closed():
                return True
            try:
                for cb in popup.locator("input[type='checkbox']").all():
                    if not cb.is_checked():
                        cb.check()
            except Exception:
                pass
            for txt in ["Continuar", "Permitir", "Continue", "Allow"]:
                try:
                    btn = popup.locator(f"button:has-text('{txt}'), div[role='button']:has-text('{txt}')")
                    if btn.count() > 0 and btn.first.is_visible():
                        btn.first.click()
                        time.sleep(1)
                        break
                except Exception:
                    pass
        return popup.is_closed()
    except Exception:
        return False



def connect_runtime_if_needed(page: Any) -> bool:
    """Ensure the Colab runtime kernel is connected."""
    try:
        return page.evaluate("""() => {
            const btn = document.querySelector('colab-connect-button');
            if (btn && btn.shadowRoot) {
                const conn = btn.shadowRoot.querySelector('#connect, #connect-button, button');
                if (conn && (conn.innerText.includes('Conectar') || conn.innerText.includes('Reconectar') || conn.innerText.includes('Connect'))) {
                    conn.click();
                    return true;
                }
            }
            if (btn) {
                btn.click();
                return true;
            }
            return false;
        }""")
    except Exception:
        return False


def get_notebook_dom_state(page: Any, target_keywords: Optional[List[str]] = None) -> Dict[str, Any]:
    """Inspect the Colab notebook DOM and extract runtime and cell execution state."""
    if target_keywords is None:
        target_keywords = ["Remessa 2", "run_selfplay_colab.sh", "sp_v", "zchezz", "selfplay"]

    return page.evaluate("""(keywords) => {
        const curUrl = window.location.href || '';
        const bodyText = document.body ? (document.body.innerText || '') : '';
        if (curUrl.includes('accounts.google.com') || curUrl.includes('signin') || bodyText.includes('Confirme que') || bodyText.includes('Confirm it')) {
            return {
                statusText: 'Auth Required (Google Login)',
                kConnected: false,
                running: false,
                pending: false,
                targetIndex: -1,
                outText: 'Google account requires verification (Confirm it is you).'
            };
        }

        const btn = document.querySelector('colab-connect-button');
        const sr = btn ? btn.shadowRoot : null;
        const connBtn = sr ? sr.querySelector('#connect') : null;
        const statusText = connBtn ? connBtn.innerText.trim() : (btn ? btn.innerText.trim() : 'no button');

        const k = typeof colab !== 'undefined' && colab.global && colab.global.notebook ? colab.global.notebook.kernel : null;
        const kConnected = k && k.isConnected ? k.isConnected() : false;

        const cells = typeof colab !== 'undefined' && colab.global && colab.global.notebook && colab.global.notebook.cells ? colab.global.notebook.cells : [];
        let targetCell = null;
        let targetIndex = -1;

        // Search backward for target cell matching keywords
        for (let i = cells.length - 1; i >= 0; i--) {
            const txt = (cells[i] && typeof cells[i].getText === 'function') ? cells[i].getText() : '';
            for (const kw of keywords) {
                if (txt.includes(kw)) {
                    targetCell = cells[i];
                    targetIndex = i;
                    break;
                }
            }
            if (targetCell) break;
        }

        // DOM fallback if model is unavailable
        if (!targetCell) {
            const domCells = Array.from(document.querySelectorAll('colab-cell'));
            for (let i = domCells.length - 1; i >= 0; i--) {
                const txt = domCells[i].innerText || '';
                for (const kw of keywords) {
                    if (txt.includes(kw)) {
                        targetIndex = i;
                        break;
                    }
                }
                if (targetIndex >= 0) break;
            }
            if (targetIndex === -1 && domCells.length > 0) {
                targetIndex = domCells.length - 1;
            }
        }

        const isRunningBtn = Array.from(document.querySelectorAll(
            'colab-run-button[title*="Interromper"], colab-run-button[aria-label*="Interromper"], ' +
            'colab-run-button[title*="Interrupt"], colab-run-button[aria-label*="Interrupt"], ' +
            'colab-run-button[title*="Stop"], colab-run-button[aria-label*="Stop"], ' +
            'colab-run-button.running, .cell-execution-container .cell-icon.running'
        ));

        let shadowRunning = false;
        const allRunBtns = Array.from(document.querySelectorAll('colab-run-button'));
        for (const b of allRunBtns) {
            const attr = ((b.getAttribute('aria-label') || '') + ' ' + (b.getAttribute('title') || '')).toLowerCase();
            if (attr.includes('interrupt') || attr.includes('interromper') || attr.includes('stop')) {
                shadowRunning = true;
                break;
            }
            if (b.shadowRoot) {
                const act = b.shadowRoot.querySelector('.cell-execution.running, md-circular-progress, [indeterminate], #stop-symbol, .stop-button, .running');
                const inner = (b.shadowRoot.innerHTML || '').toLowerCase();
                if (act || inner.includes('interrupt') || inner.includes('interromper') || inner.includes('circular-progress') || inner.includes('stop-symbol')) {
                    shadowRunning = true;
                    break;
                }
            }
        }

        const nb = typeof colab !== 'undefined' && colab.global ? colab.global.notebook : null;
        let running = isRunningBtn.length > 0 || shadowRunning;
        if (nb && typeof nb.isExecuting === 'function') {
            running = running || nb.isExecuting();
        }
        let pending = false;
        let outText = '';

        if (targetCell) {
            running = running || (targetCell.isRunning ? targetCell.isRunning() : false);
            pending = targetCell.isPending ? targetCell.isPending() : false;
            const dom = targetCell.getElement ? targetCell.getElement() : (targetCell.element_ || targetCell.dom_);
            const outDiv = dom ? dom.querySelector('.output, colab-output, .output-stream, .output_text, .output-content') : null;
            outText = outDiv ? outDiv.innerText.slice(-1200) : '';
        } else {
            const streams = Array.from(document.querySelectorAll('.output-stream, .output_text, colab-output, .output-content'));
            if (streams.length > 0) {
                outText = streams[streams.length - 1].innerText.slice(-1200);
            }
        }

        return {
            statusText,
            kConnected,
            running,
            pending,
            targetIndex,
            outText
        };
    }""", target_keywords)

    if not res.get("outText") and hasattr(page, "frames"):
        for f in page.frames:
            try:
                txt = f.inner_text("body", timeout=300).strip()
                if txt and not any(k in txt for k in ["reCAPTCHA", "RotateCookiesPage", "zchezz_selfplay"]):
                    res["outText"] = txt[-1200:]
                    break
            except Exception:
                pass

    return res



def trigger_cell_execution(
    page: Any,
    worker_or_id: Any,
    bootloader_template: Optional[str] = None,
    target_keywords: Optional[List[str]] = None,
) -> bool:
    """Inject bootloader code into the Colab target cell if template is given, and trigger execution."""
    new_code: Optional[str] = None
    if bootloader_template:
        if isinstance(worker_or_id, dict):
            wid = worker_or_id.get("worker_id", "")
            profile = worker_or_id.get("profile", str(wid))
            account_id = worker_or_id.get("account_id", 1)
            fmt_kwargs = {**worker_or_id, "worker_id": wid, "profile": profile, "account_id": account_id}
            new_code = bootloader_template.format(**fmt_kwargs)
        else:
            try:
                from config import WORKERS
                w = WORKERS.get(worker_or_id, {})
            except Exception:
                w = {}
            fmt_kwargs = {
                "worker_id": worker_or_id,
                "profile": w.get("profile", "v507"),
                "account_id": w.get("account_id", worker_or_id),
            }
            new_code = bootloader_template.format(**fmt_kwargs)

    if target_keywords is None:
        if isinstance(worker_or_id, dict) and "target_keywords" in worker_or_id:
            target_keywords = worker_or_id["target_keywords"]
        else:
            target_keywords = ["Remessa 2", "run_selfplay_colab.sh", "sp_v", "zchezz", "selfplay", "run_colab_worker.py"]

    try:
        res = page.evaluate("""(data) => {
            const { newCode, keywords } = data;
            const nb = typeof colab !== 'undefined' && colab.global ? colab.global.notebook : null;
            if (!nb || !nb.cells || nb.cells.length === 0) return { success: false, reason: 'no_cells' };

            const cells = nb.cells;
            let targetCell = null;
            for (let i = cells.length - 1; i >= 0; i--) {
                const txt = cells[i].getText ? cells[i].getText() : '';
                for (const kw of keywords) {
                    if (txt.includes(kw)) {
                        targetCell = cells[i];
                        break;
                    }
                }
                if (targetCell) break;
            }
            if (!targetCell) {
                targetCell = cells[cells.length - 1];
            }

            if (targetCell.isRunning && targetCell.isRunning()) {
                return { success: true, alreadyRunning: true };
            }

            if (newCode) {
                if (targetCell.model && targetCell.model.setText) {
                    targetCell.model.setText(newCode);
                }
                if (targetCell.model && targetCell.model.removeOutputs) {
                    targetCell.model.removeOutputs();
                }

                if (typeof monaco !== 'undefined') {
                    for (const m of monaco.editor.getModels()) {
                        const val = m.getValue ? m.getValue() : '';
                        for (const kw of keywords) {
                            if (val.includes(kw)) {
                                m.setValue(newCode);
                                break;
                            }
                        }
                    }
                }
            }

            const elem = targetCell.getElement ? targetCell.getElement() : (targetCell.element_ || targetCell.dom_);
            if (elem && elem.scrollIntoView) elem.scrollIntoView();

            if (typeof targetCell.manualExecute === 'function') {
                targetCell.manualExecute();
                return { success: true, method: 'manualExecute' };
            } else if (elem) {
                const btn = elem.querySelector('colab-run-button');
                if (btn) {
                    if (btn.shadowRoot) {
                        const inner = btn.shadowRoot.querySelector('button, [role="button"]');
                        if (inner) inner.click();
                        else btn.click();
                    } else {
                        btn.click();
                    }
                    return { success: true, method: 'colab-run-button' };
                }
            }
            return { success: false, reason: 'no_run_method' };
        }""", {"newCode": new_code, "keywords": target_keywords})
        time.sleep(3)
        dismiss_modals(page)
        return res.get("success", False) if isinstance(res, dict) else False
    except Exception:
        return False
