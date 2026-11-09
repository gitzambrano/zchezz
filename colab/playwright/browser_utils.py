"""Browser session utilities and safe Playwright helpers for Colab automation in Zchezz.

Provides CDP connection fallback, profile lock detection, modal handling,
DOM state inspection, and safe cell execution primitives without terminating
active Chrome processes.
"""

import sys as _sys
from pathlib import Path as _Path
_repo_root = _Path(__file__).resolve().parents[2]
if str(_repo_root) not in _sys.path:
    _sys.path.insert(0, str(_repo_root))


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
        mirror_dir = Path(__file__).resolve().parents[1] / "cookies"
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
            Path(__file__).resolve().parents[1] / "cookies" / f"{Path(profile_dir).name}_cookies.json",
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


def find_profile_process(profile_dir: str) -> Tuple[bool, Optional[int], Optional[int]]:
    """Check if any running chrome.exe process is currently using profile_dir.
    Returns (in_use, pid, cdp_port).
    """
    import re
    norm_target = os.path.normcase(os.path.abspath(profile_dir))
    found_pid = None
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if "chrome" in (proc.info.get("name") or "").lower():
                cmdline = proc.info.get("cmdline") or []
                if any(norm_target in os.path.normcase(arg) for arg in cmdline):
                    found_pid = proc.info.get("pid")
                    for arg in cmdline:
                        m = re.search(r"--remote-debugging-port=(\d+)", arg)
                        if m:
                            return True, found_pid, int(m.group(1))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if found_pid is not None:
        return True, found_pid, None
    return False, None, None


def is_profile_in_use(profile_dir: str) -> Tuple[bool, Optional[int]]:
    """Check if any running chrome.exe process is currently using the specified user data directory."""
    in_use, pid, _ = find_profile_process(profile_dir)
    return in_use, pid


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


_WHISPER_MODEL = None


def transcribe_audio_bytes(raw_bytes: bytes) -> str:
    """Transcribe raw audio bytes using the Whisper tiny model."""
    global _WHISPER_MODEL
    try:
        import io
        import soundfile as sf
        import scipy.signal
        import whisper

        if _WHISPER_MODEL is None:
            _WHISPER_MODEL = whisper.load_model("tiny")

        bio = io.BytesIO(raw_bytes)
        data, sr = sf.read(bio, dtype="float32")
        if len(data.shape) > 1:
            data = data.mean(axis=1)
        if sr != 16000:
            num_samples = int(len(data) * 16000 / sr)
            data = scipy.signal.resample(data, num_samples)

        result = _WHISPER_MODEL.transcribe(data, fp16=False)
        return result.get("text", "").strip()
    except Exception as exc:
        print(f"  [WHISPER ERROR] {exc}", flush=True)
        return ""


def solve_recaptcha_playwright(page: Any) -> bool:
    """Detect and solve Google reCAPTCHA v2 challenges via audio fallback and Whisper."""
    try:
        anchor_frame = page.frame_locator("iframe[src*='anchor']")
        anchor = anchor_frame.locator("#recaptcha-anchor")
        if anchor.count() == 0:
            return False

        try:
            if anchor.get_attribute("aria-checked", timeout=2000) == "true":
                return True
        except Exception:
            pass

        print("  [reCAPTCHA] Clicking anchor checkbox...", flush=True)
        anchor.click(timeout=5000)
        time.sleep(3)

        try:
            if anchor.get_attribute("aria-checked", timeout=2000) == "true":
                print("  [reCAPTCHA] Checkbox checked immediately.", flush=True)
                return True
        except Exception:
            pass

        bframe = page.frame_locator("iframe[src*='bframe']")
        audio_btn = bframe.locator("#recaptcha-audio-button")
        if audio_btn.count() > 0 and audio_btn.first.is_visible():
            print("  [reCAPTCHA] Triggering audio challenge...", flush=True)
            audio_btn.first.click()
            time.sleep(4)

        dl_link = bframe.locator("a.rc-audiochallenge-tdownload-link, a[href*='payload'], a[href*='audio.mp3']")
        if dl_link.count() > 0:
            audio_url = dl_link.first.get_attribute("href")
            print(f"  [reCAPTCHA] Downloading audio challenge: {audio_url[:60]}...", flush=True)
            resp = page.request.get(audio_url)
            audio_bytes = resp.body()

            text = transcribe_audio_bytes(audio_bytes)
            print(f"  [reCAPTCHA] Transcribed text: '{text}'", flush=True)

            audio_input = bframe.locator("#audio-response")
            if text and audio_input.count() > 0:
                audio_input.fill(text)
                time.sleep(1)
                verify_btn = bframe.locator("#recaptcha-verify-button")
                if verify_btn.count() > 0:
                    print("  [reCAPTCHA] Submitting verification...", flush=True)
                    verify_btn.click()
                    time.sleep(4)

        try:
            status = anchor.get_attribute("aria-checked", timeout=3000)
            return status == "true"
        except Exception:
            return True
    except Exception as exc:
        print(f"  [reCAPTCHA ERROR] {exc}", flush=True)
        return False


def solve_google_challenge_if_needed(page: Any, target_account: Optional[str] = None, notebook_url: Optional[str] = None) -> bool:
    """Handle Google authentication prompts, account chooser, reCAPTCHA, and OAuth consent."""
    try:
        url = getattr(page, "url", "") or ""
        if "accounts.google.com" not in url:
            return False

        # Recover from rejected sign-in by reloading the notebook
        if "signin/rejected" in url:
            if notebook_url:
                print(f"  [AUTH] Rejected sign-in detected. Resetting to {notebook_url[:50]}...", flush=True)
                page.goto(notebook_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(3)
                url = getattr(page, "url", "") or ""
            else:
                return False

        # 1. Select account if account chooser is displayed
        if "accountchooser" in url or "ServiceLogin" in url:
            if target_account:
                for sel in [
                    f"div[data-identifier*='{target_account}']",
                    f"div[data-email*='{target_account}']",
                    f"div.UXFQgc:has-text('{target_account}')",
                    f"div.xKcayf:has-text('{target_account}')",
                    f"li:has-text('{target_account}')",
                    f"div[role='link']:has-text('{target_account}')",
                    f"div[role='button']:has-text('{target_account}')",
                    f"text={target_account}",
                ]:
                    try:
                        loc = page.locator(sel)
                        if loc.count() > 0 and loc.first.is_visible():
                            print(f"  [AUTH] Selecting account {target_account}...", flush=True)
                            loc.first.click()
                            time.sleep(3)
                            break
                    except Exception:
                        pass

        # 2. Check for reCAPTCHA before clicking any advance button
        anchor_frame = page.frame_locator("iframe[src*='anchor']")
        has_anchor = anchor_frame.locator("#recaptcha-anchor").count() > 0
        if has_anchor:
            print("  [AUTH] reCAPTCHA challenge detected. Solving...", flush=True)
            solve_recaptcha_playwright(page)
            time.sleep(2)

        # 3. Check if reCAPTCHA is verified before advancing
        anchor_checked = False
        if has_anchor:
            try:
                anchor_checked = anchor_frame.locator("#recaptcha-anchor").get_attribute("aria-checked", timeout=2000) == "true"
            except Exception:
                anchor_checked = True

        # 4. Check if a password field is present and empty
        pwd_input = page.locator("input[type='password']")
        if pwd_input.count() > 0:
            try:
                if not pwd_input.first.input_value():
                    return False
            except Exception:
                pass

        # Check OAuth scope checkboxes (e.g. Google Drive access)
        try:
            for cb in page.locator("input[type='checkbox']").all():
                if not cb.is_checked():
                    cb.check()
                    time.sleep(1)
        except Exception:
            pass

        if not has_anchor or anchor_checked:
            action_buttons = [
                "Avançar", "Continuar", "Permitir", "Continue", "Allow", "Next",
                "Entrar", "Sim, sou eu", "Confirmar", "Confirm", "Acessar"
            ]
            for txt in action_buttons:
                try:
                    btn = page.locator(f"button:has-text('{txt}'), div[role='button']:has-text('{txt}'), input[type='submit'][value*='{txt}']")
                    if btn.count() > 0 and btn.first.is_visible():
                        print(f"  [AUTH] Clicking '{txt}'...", flush=True)
                        btn.first.click()
                        time.sleep(4)
                        break
                except Exception:
                    pass

        return True
    except Exception as exc:
        print(f"  [AUTH ERROR] {exc}", flush=True)
        return False


def handle_google_oauth_popup(popup: Any, target_account: Optional[str] = None, notebook_url: Optional[str] = None) -> bool:
    """Handle Google OAuth consent dialog popup or page for Google Drive connection."""
    return solve_google_challenge_if_needed(popup, target_account=target_account, notebook_url=notebook_url)



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
    force: bool = False,
) -> bool:
    """Inject bootloader code into the Colab target cell if template is given, and trigger execution."""
    new_code: Optional[str] = None
    if bootloader_template:
        if isinstance(worker_or_id, dict):
            wid = worker_or_id.get("worker_id", "")
            profile = worker_or_id.get("profile", str(wid))
            account_id = worker_or_id.get("account_id", 1)
            drive_dir = worker_or_id.get("drive_dir", "")
            positions = worker_or_id.get("positions", "")
            extra_args = worker_or_id.get("extra_args", "")
            cmd_args = f"--positions {positions}" if positions else ""
            if extra_args:
                cmd_args = f"{cmd_args} {extra_args}".strip()
            fmt_kwargs = {
                **worker_or_id,
                "worker_id": wid,
                "profile": profile,
                "account_id": account_id,
                "drive_dir": drive_dir,
                "positions": positions,
                "cmd_args": cmd_args,
            }
            new_code = bootloader_template.format(**fmt_kwargs)
        else:
            try:
                try:
                    from colab.config import WORKERS
                except ImportError:
                    from colab.config import WORKERS
                w = WORKERS.get(worker_or_id, {})
            except Exception:
                w = {}
            drive_dir = w.get("drive_dir", "/content/drive/MyDrive/zquoridor_data/selfplay_contact_soup_858")
            positions = w.get("positions", "")
            extra_args = w.get("extra_args", "")
            cmd_args = f"--positions {positions}" if positions else ""
            if extra_args:
                cmd_args = f"{cmd_args} {extra_args}".strip()
            fmt_kwargs = {
                "worker_id": worker_or_id,
                "profile": worker_or_id,
                "drive_dir": drive_dir,
                "positions": positions,
                "cmd_args": cmd_args,
            }
            new_code = bootloader_template.format(**fmt_kwargs)

    if target_keywords is None:
        if isinstance(worker_or_id, dict) and "target_keywords" in worker_or_id:
            target_keywords = list(worker_or_id["target_keywords"])
        else:
            target_keywords = ["run_colab_worker.py", "selfplay_targeted_weakness", "selfplay_15m", "zquoridor", "Remessa 2", "zchezz"]

    if "zchezz" not in target_keywords:
        target_keywords.append("zchezz")

    try:
        res = page.evaluate("""(data) => {
            const { newCode, keywords, force } = data;
            const nb = typeof colab !== 'undefined' && colab.global ? colab.global.notebook : null;
            if (!nb || !nb.cells || nb.cells.length === 0) return { success: false, reason: 'no_cells' };

            const cells = nb.cells;
            let targetCell = null;
            if (keywords && keywords.length > 0) {
                for (let i = 0; i < cells.length; i++) {
                    const txt = cells[i].getText ? cells[i].getText() : '';
                    if (txt.includes(keywords[0])) {
                        targetCell = cells[i];
                        break;
                    }
                }
            }
            if (!targetCell) {
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
            }
            if (!targetCell) {
                targetCell = cells[0];
            }

            const elem = targetCell.getElement ? targetCell.getElement() : (targetCell.element_ || targetCell.dom_);
            const oldText = targetCell.getText ? targetCell.getText() : '';
            const matchesKeywords = keywords.some(kw => oldText.includes(kw));

            if (targetCell.isRunning && targetCell.isRunning()) {
                if (!force && matchesKeywords) {
                    return { success: true, alreadyRunning: true };
                }
                if (typeof targetCell.interrupt === 'function') {
                    try { targetCell.interrupt(); } catch (e) {}
                }
                if (nb && typeof nb.interrupt === 'function') {
                    try { nb.interrupt(); } catch (e) {}
                }
                if (elem) {
                    const stopBtn = elem.querySelector('colab-run-button.running, colab-run-button[aria-label*="Interromper"], colab-run-button[title*="Interromper"]');
                    if (stopBtn) {
                        try { stopBtn.click(); } catch (e) {}
                    }
                }
            }

            if (newCode) {
                if (typeof targetCell.setText === 'function') {
                    targetCell.setText(newCode);
                }
                if (targetCell.model && typeof targetCell.model.setText === 'function') {
                    targetCell.model.setText(newCode);
                }
                if (targetCell.model && targetCell.model.textModel && typeof targetCell.model.textModel.setValue === 'function') {
                    targetCell.model.textModel.setValue(newCode);
                }
                if (targetCell.model && typeof targetCell.model.removeOutputs === 'function') {
                    targetCell.model.removeOutputs();
                }

                if (typeof monaco !== 'undefined') {
                    let updatedMonaco = false;
                    for (const m of monaco.editor.getModels()) {
                        const val = m.getValue ? m.getValue() : '';
                        if (val === oldText || (oldText && val.includes(oldText.slice(0, 30)))) {
                            m.setValue(newCode);
                            updatedMonaco = true;
                            break;
                        }
                    }
                    if (!updatedMonaco) {
                        for (const m of monaco.editor.getModels()) {
                            const val = m.getValue ? m.getValue() : '';
                            for (const kw of keywords) {
                                if (val.includes(kw)) {
                                    m.setValue(newCode);
                                    updatedMonaco = true;
                                    break;
                                }
                            }
                            if (updatedMonaco) break;
                        }
                    }
                    if (!updatedMonaco && monaco.editor.getModels().length > 0) {
                        const models = monaco.editor.getModels();
                        models[models.length - 1].setValue(newCode);
                    }
                }
            }

            if (typeof nb !== 'undefined' && typeof nb.save === 'function') {
                try { nb.save(); } catch (e) {}
            }

            if (elem && elem.scrollIntoView) elem.scrollIntoView();

            let executed = false;
            if (elem) {
                const btn = elem.querySelector('colab-run-button');
                if (btn) {
                    if (btn.shadowRoot) {
                        const inner = btn.shadowRoot.querySelector('#run-button, button, [role="button"]');
                        if (inner) {
                            inner.click();
                            executed = true;
                        } else {
                            btn.click();
                            executed = true;
                        }
                    } else {
                        btn.click();
                        executed = true;
                    }
                }
            }
            if (typeof targetCell.manualExecute === 'function') {
                try {
                    targetCell.manualExecute();
                    executed = true;
                } catch (e) {}
            }
            return { success: executed, method: 'run-button' };
        }""", {"newCode": new_code, "keywords": target_keywords, "force": force})
        time.sleep(3)
        dismiss_modals(page)
        return res.get("success", False) if isinstance(res, dict) else False
    except Exception:
        return False
