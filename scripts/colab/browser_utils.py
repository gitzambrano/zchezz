"""Browser session utilities and safe Playwright helpers for Colab automation.

Provides CDP connection fallback, profile lock detection, modal handling,
DOM state inspection, and safe cell execution primitives without terminating
active Chrome processes.
"""

import os
import socket
import time
from typing import Dict, Any, Optional, Tuple, List
import psutil


def is_cdp_reachable(port: int, host: str = "127.0.0.1", timeout: float = 1.0) -> bool:
    """Check whether a Chrome DevTools Protocol port is open and accepting connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def is_profile_in_use(profile_dir: str) -> Tuple[bool, Optional[int]]:
    """Check if any running chrome.exe process is currently using the specified user data directory."""
    target_name = os.path.basename(os.path.normpath(profile_dir)).lower()
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            p_name = proc.info.get("name") or ""
            if "chrome" in p_name.lower():
                cmdline = proc.info.get("cmdline") or []
                cmd_str = " ".join(cmdline).lower()
                if target_name in cmd_str and ("user-data-dir" in cmd_str or "profile" in cmd_str):
                    return True, proc.info.get("pid")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False, None


def dismiss_modals(page: Any) -> bool:
    """Detect and click common Colab warning and authorization confirmation dialogs."""
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


def connect_runtime_if_needed(page: Any) -> bool:
    """Ensure the Colab runtime kernel is connected."""
    try:
        return page.evaluate("""() => {
            const btn = document.querySelector('colab-connect-button');
            if (btn && btn.shadowRoot) {
                const conn = btn.shadowRoot.querySelector('#connect');
                if (conn && (conn.innerText.includes('Conectar') || conn.innerText.includes('Reconectar') || conn.innerText.includes('Connect'))) {
                    conn.click();
                    return true;
                }
            }
            return false;
        }""")
    except Exception:
        return False


def get_notebook_dom_state(page: Any, target_keywords: Optional[List[str]] = None) -> Dict[str, Any]:
    """Inspect the Colab notebook DOM and extract runtime and cell execution state."""
    if target_keywords is None:
        target_keywords = ["run_colab_worker.py", "selfplay_15m", "Remessa 2", "selfplay"]

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
            'colab-run-button[title*="Interromper"], colab-run-button[aria-label*="Interromper"], colab-run-button.running'
        ));

        const nb = typeof colab !== 'undefined' && colab.global ? colab.global.notebook : null;
        let running = isRunningBtn.length > 0;
        if (nb && typeof nb.isExecuting === 'function') {
            running = running || nb.isExecuting();
        }
        let pending = false;
        let outText = '';

        if (targetCell) {
            running = running || (targetCell.isRunning ? targetCell.isRunning() : false);
            pending = targetCell.isPending ? targetCell.isPending() : false;
            const dom = targetCell.getElement ? targetCell.getElement() : (targetCell.element_ || targetCell.dom_);
            const outDiv = dom ? dom.querySelector('.output, colab-output, .output-stream, .output_text') : null;
            outText = outDiv ? outDiv.innerText.slice(-1200) : '';
        } else {
            const streams = Array.from(document.querySelectorAll('.output-stream, .output_text, colab-output'));
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
            new_code = bootloader_template.format(worker_id=worker_or_id, profile=worker_or_id)

    if target_keywords is None:
        if isinstance(worker_or_id, dict) and "target_keywords" in worker_or_id:
            target_keywords = worker_or_id["target_keywords"]
        else:
            target_keywords = ["run_colab_worker.py", "selfplay_15m", "zquoridor", "Remessa 2", "zchezz"]

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
