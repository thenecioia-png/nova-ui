#!/usr/bin/env python3
"""N.O.V.A BOT LOCAL - Agente de PC para Denison The Necio"""

import sys, os, json, time, base64, platform, subprocess, configparser, threading
from io import BytesIO
from pathlib import Path
from datetime import datetime

# ── Auto-install dependencies ─────────────────────────────────────────────────
def install(pkg, imp=None):
    try:
        __import__(imp or pkg)
    except ImportError:
        print(f"Instalando {pkg}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

for p, i in [("pyautogui", None), ("requests", None), ("pyperclip", None), ("psutil", None), ("Pillow", "PIL")]:
    install(p, i)

import requests, pyautogui, pyperclip, psutil
try:
    from PIL import ImageGrab
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

# ── Live vision globals ────────────────────────────────────────────────────────
_live_vision_active = False
_live_vision_thread = None
_push_frame_url     = None
_push_frame_headers = None

# ── Config: accept args from command line or ask ──────────────────────────────
CONFIG_FILE = Path.home() / ".nova_bot.json"

def get_config():
    # Accept: python nova_bot.py <url> <apikey>
    if len(sys.argv) == 3:
        cfg = {"server_url": sys.argv[1].rstrip("/"), "api_key": sys.argv[2]}
        with open(CONFIG_FILE, "w") as f: json.dump(cfg, f)
        return cfg
    if CONFIG_FILE.exists():
        cfg = json.loads(CONFIG_FILE.read_text())
        print(f"Usando config guardada: {cfg['server_url']}")
        return cfg
    print("\nN.O.V.A BOT — Configuración inicial")
    url = input("URL del servidor: ").strip().rstrip("/")
    key = input("API Key: ").strip()
    cfg = {"server_url": url, "api_key": key}
    CONFIG_FILE.write_text(json.dumps(cfg))
    return cfg

# ── Command handlers ──────────────────────────────────────────────────────────

def do_screenshot(p):
    try:
        img = ImageGrab.grab() if HAS_PIL else pyautogui.screenshot()
        buf = BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        return {"ok": True, "imagen_b64": b64, "ancho": img.size[0], "alto": img.size[1]}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_mouse_move(p):
    try:
        pyautogui.moveTo(int(p["x"]), int(p["y"]), duration=float(p.get("duracion", 0.3)))
        return {"ok": True}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_mouse_click(p):
    try:
        x, y = p.get("x"), p.get("y")
        if x is not None: pyautogui.moveTo(int(x), int(y), duration=0.2)
        if p.get("doble"): pyautogui.doubleClick()
        else: pyautogui.click(button=p.get("boton", "left"))
        return {"ok": True}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_mouse_scroll(p):
    try:
        pyautogui.scroll(int(p.get("cantidad", 3)))
        return {"ok": True}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_keyboard_type(p):
    try:
        pyautogui.write(str(p.get("texto", "")), interval=float(p.get("intervalo", 0.03)))
        return {"ok": True}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_keyboard_press(p):
    try:
        tecla = str(p.get("tecla", "")).strip()
        if not tecla: return {"ok": False, "error": "Tecla no especificada"}
        mods = p.get("modificadores", [])
        if mods: pyautogui.hotkey(*mods, tecla)
        else: pyautogui.press(tecla)
        return {"ok": True}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_keyboard_hotkey(p):
    try:
        teclas = p.get("teclas", [])
        if not teclas: return {"ok": False, "error": "Teclas no especificadas"}
        pyautogui.hotkey(*teclas)
        return {"ok": True}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_abrir_app(p):
    try:
        app = str(p.get("app", ""))
        s = platform.system()
        if s == "Windows": subprocess.Popen(["start", app], shell=True)
        elif s == "Darwin": subprocess.Popen(["open", "-a", app])
        else: subprocess.Popen([app])
        return {"ok": True}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_run_command(p):
    try:
        r = subprocess.run(str(p.get("comando", "")), shell=True, capture_output=True, text=True, timeout=int(p.get("timeout", 15)))
        return {"ok": True, "stdout": r.stdout[:3000], "stderr": r.stderr[:500], "codigo": r.returncode}
    except subprocess.TimeoutExpired: return {"ok": False, "error": "Timeout"}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_copiar_texto(p):
    try:
        pyperclip.copy(str(p.get("texto", "")))
        return {"ok": True}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_pegar_texto(p):
    try:
        pyautogui.hotkey("ctrl", "v")
        return {"ok": True}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_get_clipboard(p):
    try:
        contenido = pyperclip.paste()
        return {"ok": True, "contenido": contenido}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_get_screen_info(p):
    try:
        w, h = pyautogui.size()
        x, y = pyautogui.position()
        return {"ok": True, "pantalla": {"ancho": w, "alto": h}, "cursor": {"x": x, "y": y}}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_get_processes(p):
    try:
        procs = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try: procs.append(proc.info)
            except: pass
        procs.sort(key=lambda p: p.get("cpu_percent", 0) or 0, reverse=True)
        return {"ok": True, "procesos": procs[:30]}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_abrir_url(p):
    try:
        import webbrowser
        webbrowser.open(str(p.get("url", "")))
        return {"ok": True}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_escribir_archivo(p):
    try:
        ruta = Path(p.get("ruta", ""))
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(str(p.get("contenido", "")), encoding="utf-8")
        return {"ok": True, "ruta": str(ruta)}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_leer_archivo(p):
    try:
        ruta = Path(p.get("ruta", ""))
        if not ruta.exists(): return {"ok": False, "error": "Archivo no encontrado"}
        return {"ok": True, "contenido": ruta.read_text(encoding="utf-8")[:5000]}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_sleep(p):
    try:
        time.sleep(min(float(p.get("segundos", 1)), 30))
        return {"ok": True}
    except Exception as e: return {"ok": False, "error": str(e)}

# ── Live vision streaming ─────────────────────────────────────────────────────
def _live_capture_loop(fps):
    global _live_vision_active
    delay = max(1.0 / max(fps, 1), 0.05)
    while _live_vision_active:
        try:
            shot = pyautogui.screenshot()
            buf  = BytesIO()
            shot.convert("RGB").save(buf, format="JPEG", quality=35, optimize=True, subsampling=2)
            frame_b64 = base64.b64encode(buf.getvalue()).decode()
            requests.post(
                _push_frame_url,
                json={"frame_b64": frame_b64},
                headers=_push_frame_headers,
                timeout=4
            )
        except Exception:
            pass
        time.sleep(delay)

def do_iniciar_vision_live(p):
    global _live_vision_active, _live_vision_thread
    fps = min(int(p.get("fps", 8)), 20)
    _live_vision_active = True
    if _live_vision_thread is None or not _live_vision_thread.is_alive():
        _live_vision_thread = threading.Thread(target=_live_capture_loop, args=(fps,), daemon=True)
        _live_vision_thread.start()
    return {"ok": True, "fps": fps, "mensaje": f"Visión en vivo iniciada a {fps} FPS"}

def do_detener_vision_live(p):
    global _live_vision_active
    _live_vision_active = False
    return {"ok": True, "mensaje": "Visión en vivo detenida"}

def do_escanear_red(p):
    """Muestra conexiones de red activas en la PC."""
    try:
        import socket
        conexiones = []
        for conn in psutil.net_connections(kind="inet"):
            try:
                estado  = conn.status or "N/A"
                laddr   = f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else "-"
                raddr   = f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else "-"
                pid     = conn.pid or 0
                nombre  = ""
                if pid:
                    try: nombre = psutil.Process(pid).name()
                    except: pass
                conexiones.append({"local": laddr, "remoto": raddr, "estado": estado, "pid": pid, "proceso": nombre})
            except: pass
        conexiones.sort(key=lambda c: c["estado"])
        suspicious = [c for c in conexiones if c["remoto"] != "-" and not c["remoto"].startswith("127.")]
        return {"ok": True, "conexiones": conexiones[:50], "externas": suspicious[:20], "total": len(conexiones)}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_antivirus_scan(p):
    """Escanea un archivo o carpeta buscando indicadores de malware básicos."""
    try:
        ruta = Path(p.get("ruta", "."))
        resultados = []
        SOSPECHOSOS = [
            ".exe", ".bat", ".cmd", ".vbs", ".ps1", ".scr", ".pif", ".com",
            ".dll", ".sys", ".drv", ".msi", ".jar", ".wsf", ".hta"
        ]
        PALABRAS_CLAVE = [b"powershell", b"cmd.exe", b"WScript", b"CreateObject", b"shell.run",
                          b"base64", b"eval(", b"exec(", b"HKEY_", b"RegWrite", b"Download"]

        archivos = list(ruta.rglob("*"))[:200] if ruta.is_dir() else [ruta]
        for arch in archivos:
            if not arch.is_file(): continue
            alertas = []
            if arch.suffix.lower() in SOSPECHOSOS:
                alertas.append(f"extensión sospechosa: {arch.suffix}")
            try:
                tamano = arch.stat().st_size
                if tamano > 0 and tamano < 5_000_000:
                    contenido = arch.read_bytes()
                    for kw in PALABRAS_CLAVE:
                        if kw in contenido:
                            alertas.append(f"contiene: {kw.decode(errors='replace')}")
            except: pass
            if alertas:
                resultados.append({"archivo": str(arch), "alertas": alertas})

        return {
            "ok": True,
            "archivos_analizados": len(archivos),
            "amenazas_detectadas": len(resultados),
            "detalle": resultados[:20],
            "estado": "⚠️ AMENAZAS ENCONTRADAS" if resultados else "✅ Sin amenazas detectadas"
        }
    except Exception as e: return {"ok": False, "error": str(e)}

def do_info_sistema(p):
    """Información completa del sistema: CPU, RAM, disco, OS."""
    try:
        import platform as plat
        cpu_pct  = psutil.cpu_percent(interval=1)
        ram      = psutil.virtual_memory()
        disco    = psutil.disk_usage("C:\\" if platform.system() == "Windows" else "/")
        return {
            "ok": True,
            "os": f"{plat.system()} {plat.release()} ({plat.machine()})",
            "cpu_porcentaje": cpu_pct,
            "ram_total_gb": round(ram.total / 1e9, 2),
            "ram_usada_gb": round(ram.used / 1e9, 2),
            "ram_porcentaje": ram.percent,
            "disco_total_gb": round(disco.total / 1e9, 2),
            "disco_libre_gb": round(disco.free / 1e9, 2),
            "disco_porcentaje": disco.percent,
        }
    except Exception as e: return {"ok": False, "error": str(e)}

HANDLERS = {
    "screenshot":       do_screenshot,
    "mouse_move":       do_mouse_move,
    "mouse_click":      do_mouse_click,
    "mouse_scroll":     do_mouse_scroll,
    "keyboard_type":    do_keyboard_type,
    "keyboard_press":   do_keyboard_press,
    "keyboard_hotkey":  do_keyboard_hotkey,
    "abrir_app":        do_abrir_app,
    "run_command":      do_run_command,
    "copiar_texto":     do_copiar_texto,
    "pegar_texto":      do_pegar_texto,
    "get_clipboard":    do_get_clipboard,
    "get_screen_info":  do_get_screen_info,
    "get_processes":    do_get_processes,
    "abrir_url":        do_abrir_url,
    "escribir_archivo": do_escribir_archivo,
    "leer_archivo":     do_leer_archivo,
    "sleep":            do_sleep,
    "escanear_red":          do_escanear_red,
    "antivirus_scan":        do_antivirus_scan,
    "info_sistema":          do_info_sistema,
    "iniciar_vision_live":   do_iniciar_vision_live,
    "detener_vision_live":   do_detener_vision_live,
}

# ── Main loop ─────────────────────────────────────────────────────────────────

def run(cfg):
    global _push_frame_url, _push_frame_headers

    url     = cfg["server_url"]
    headers = {"x-bot-api-key": cfg["api_key"], "Content-Type": "application/json"}
    poll    = f"{url}/api/bot/commands/pending"
    result  = lambda cid: f"{url}/api/bot/commands/{cid}/resultado"
    errors  = 0

    # Set live vision push URL for the background thread
    _push_frame_url     = f"{url}/api/bot/push-frame"
    _push_frame_headers = headers

    print(f"\n✓ Bot conectado a {url}")
    print("Esperando comandos... (Ctrl+C para detener)\n")

    while True:
        try:
            r = requests.get(poll, headers=headers, timeout=10)
            if r.status_code == 401:
                print("ERROR: API Key inválida. Cierra el bot, genera una nueva key en la web y vuelve a ejecutar.")
                time.sleep(30)
                continue
            r.raise_for_status()
            errors = 0

            for cmd in r.json().get("comandos", []):
                cid, tipo, payload = cmd["id"], cmd["tipo"], cmd.get("payload", {})
                ts = datetime.now().strftime("%H:%M:%S")
                print(f"[{ts}] ▶ {tipo}  {json.dumps(payload)[:60]}")

                handler = HANDLERS.get(tipo)
                res     = handler(payload) if handler else {"ok": False, "error": f"Tipo desconocido: {tipo}"}
                estado  = "completado" if res.get("ok") else "error"

                log = {k: v for k, v in res.items() if k != "imagen_b64"}
                print(f"       {'✓' if res.get('ok') else '✗'} {estado}: {json.dumps(log)[:100]}")

                # Screenshots can be 1MB+ in base64, give them more time to upload
                upload_timeout = 60 if tipo == "screenshot" else 15
                try:
                    rr = requests.post(result(cid), headers=headers, json={"estado": estado, "resultado": res}, timeout=upload_timeout)
                    if rr.status_code == 413:
                        print("       ⚠ Imagen demasiado grande para el servidor")
                    elif not rr.ok:
                        print(f"       ⚠ Error del servidor: {rr.status_code}")
                except Exception as upload_err:
                    print(f"       ⚠ Error enviando resultado: {upload_err}")

        except KeyboardInterrupt:
            print("\nBot detenido. ¡Hasta luego!")
            break
        except Exception as e:
            errors += 1
            wait = min(2 ** errors, 30)
            print(f"Error ({errors}): {e} — reintentando en {wait}s...")
            time.sleep(wait)
            continue

        time.sleep(2)

if __name__ == "__main__":
    cfg = get_config()
    run(cfg)
