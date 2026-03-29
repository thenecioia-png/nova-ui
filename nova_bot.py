#!/usr/bin/env python3
"""N.O.V.A BOT LOCAL - Agente de PC para Denison The Necio
   v3.0 — Auto-reparación, Circuit Breaker, Heartbeat, Watchdog
"""

import sys, os, json, time, base64, platform, subprocess, configparser, threading, shlex
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
    """Escribe texto usando clipboard (más confiable con caracteres especiales/acentos)."""
    try:
        texto = str(p.get("texto", ""))
        if not texto:
            return {"ok": False, "error": "texto vacío"}
        # Use clipboard paste — handles Unicode, accents, Spanish chars perfectly
        pyperclip.copy(texto)
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "v")
        return {"ok": True, "texto": texto[:80]}
    except Exception as e:
        # Fallback to write() if clipboard fails
        try:
            pyautogui.write(texto, interval=0.04)
            return {"ok": True, "metodo": "write_fallback"}
        except Exception as e2:
            return {"ok": False, "error": str(e)}

def do_keyboard_press(p):
    try:
        mods = p.get("modificadores", [])
        if mods: pyautogui.hotkey(*mods, str(p.get("tecla", "")))
        else: pyautogui.press(str(p.get("tecla", "")))
        return {"ok": True}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_keyboard_hotkey(p):
    try:
        pyautogui.hotkey(*p.get("teclas", []))
        return {"ok": True}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_abrir_app(p):
    try:
        app = str(p.get("app", ""))
        s = platform.system()
        if s == "Windows": os.startfile(app)
        elif s == "Darwin": subprocess.Popen(["open", "-a", app])
        else: subprocess.Popen(["xdg-open", app])
        return {"ok": True}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_run_command(p):
    try:
        cmd = str(p.get("comando", "")).strip()
        timeout = int(p.get("timeout", 30))  # bumped 15→30s for compiling/npm/etc
        try:
            args = shlex.split(cmd)
        except ValueError as e:
            return {"ok": False, "error": f"Comando inválido: {e}"}
        if not args:
            return {"ok": False, "error": "Comando vacío"}
        r = subprocess.run(args, shell=False, capture_output=True, text=True, timeout=timeout)
        salida = r.stdout[:4000] or r.stderr[:2000] or "(sin salida)"
        return {
            "ok": True,
            "salida": salida,       # frontend key
            "stdout": r.stdout[:4000],  # also keep for model compatibility
            "stderr": r.stderr[:1000],
            "codigo": r.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Timeout después de {p.get('timeout', 30)}s"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

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
        ram_total = psutil.virtual_memory().total
        procs = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                info = proc.info
                mem_pct = info.get("memory_percent") or 0
                procs.append({
                    "pid":           info.get("pid", 0),
                    "nombre":        info.get("name", "desconocido"),
                    "cpu_porcentaje": round(info.get("cpu_percent", 0) or 0, 1),
                    "memoria_mb":    round(mem_pct * ram_total / 100 / 1024 / 1024, 1),
                })
            except: pass
        procs.sort(key=lambda x: x["cpu_porcentaje"], reverse=True)
        return {"ok": True, "procesos": procs[:30]}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_abrir_url(p):
    try:
        import webbrowser
        webbrowser.open(str(p.get("url", "")))
        return {"ok": True}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_navegar_a(p):
    """Navega el tab activo a una URL usando Ctrl+L (sin depender de coordenadas).
    Funciona en Chrome, Edge, Firefox — siempre, independientemente de la resolución."""
    try:
        url = str(p.get("url", ""))
        nueva_pestana = bool(p.get("nueva_pestana", False))
        time.sleep(0.2)
        if nueva_pestana:
            pyautogui.hotkey("ctrl", "t")  # abre pestaña nueva
            time.sleep(0.5)
        # Ctrl+L → enfoca la barra de direcciones en cualquier navegador Chromium
        pyautogui.hotkey("ctrl", "l")
        time.sleep(0.3)
        pyautogui.hotkey("ctrl", "a")   # selecciona todo el texto actual
        time.sleep(0.1)
        # Pega la URL via clipboard (más confiable que escribir char a char)
        pyperclip.copy(url)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.2)
        pyautogui.press("enter")
        return {"ok": True, "url": url, "nueva_pestana": nueva_pestana}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_foco_ventana(p):
    """Trae al frente una ventana por su título o proceso (Windows)."""
    try:
        titulo = str(p.get("titulo", "")).lstrip("-")
        proceso = str(p.get("proceso", "")).lstrip("-")
        sistema = platform.system()
        if sistema == "Windows":
            try:
                import ctypes
                # Intenta con pyautogui getWindowsWithTitle
                ventanas = pyautogui.getWindowsWithTitle(titulo)
                if ventanas:
                    ventanas[0].activate()
                    return {"ok": True, "ventana": ventanas[0].title}
            except Exception:
                pass
            # Fallback: Alt+Tab para ciclar ventanas
            pyautogui.hotkey("alt", "tab")
            return {"ok": True, "metodo": "alt_tab"}
        else:
            # macOS / Linux
            if proceso:
                subprocess.Popen(["open", "-a", proceso] if sistema == "Darwin" else ["wmctrl", "-a", titulo])
            return {"ok": True}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_cerrar_pestana(p):
    """Cierra el tab activo con Ctrl+W."""
    try:
        pyautogui.hotkey("ctrl", "w")
        return {"ok": True}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_tab_siguiente(p):
    """Cambia al siguiente tab con Ctrl+Tab."""
    try:
        pyautogui.hotkey("ctrl", "tab")
        return {"ok": True}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_recargar_pagina(p):
    """Recarga la página actual con Ctrl+R (o Ctrl+Shift+R para hard refresh)."""
    try:
        hard = bool(p.get("hard", False))
        if hard:
            pyautogui.hotkey("ctrl", "shift", "r")
        else:
            pyautogui.hotkey("ctrl", "r")
        return {"ok": True, "hard": hard}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_copiar_url_actual(p):
    """Copia la URL del tab activo al clipboard via Ctrl+L → Ctrl+C → Escape."""
    try:
        pyautogui.hotkey("ctrl", "l")  # enfoca barra de URL
        time.sleep(0.3)
        pyautogui.hotkey("ctrl", "a")  # selecciona todo
        time.sleep(0.1)
        pyautogui.hotkey("ctrl", "c")  # copia
        time.sleep(0.2)
        pyautogui.press("escape")      # cierra foco de barra
        url_actual = pyperclip.paste()
        return {"ok": True, "url": url_actual}
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
    from PIL import Image as PILImage
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
        disco    = psutil.disk_usage("/")
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
    # ── Navegación de browser (sin coordenadas, siempre confiable) ──────────
    "navegar_a":        do_navegar_a,        # navega tab activo a URL (Ctrl+L)
    "foco_ventana":     do_foco_ventana,     # trae ventana al frente
    "cerrar_pestana":   do_cerrar_pestana,   # Ctrl+W
    "tab_siguiente":    do_tab_siguiente,    # Ctrl+Tab
    "recargar_pagina":  do_recargar_pagina,  # Ctrl+R / Ctrl+Shift+R
    "copiar_url_actual": do_copiar_url_actual, # obtiene URL del tab activo
    # ────────────────────────────────────────────────────────────────────────
    "escribir_archivo": do_escribir_archivo,
    "leer_archivo":     do_leer_archivo,
    "sleep":            do_sleep,
    "escanear_red":          do_escanear_red,
    "antivirus_scan":        do_antivirus_scan,
    "info_sistema":          do_info_sistema,
    "iniciar_vision_live":   do_iniciar_vision_live,
    "detener_vision_live":   do_detener_vision_live,
}

# ── Circuit Breaker ────────────────────────────────────────────────────────────
class CircuitBreaker:
    """Evita ejecutar comandos que fallan repetido (Nivel 1 auto-reparación)."""
    def __init__(self, threshold=3, reset_after=60):
        self.failures   = {}   # tipo → consecutive failures
        self.blocked_at = {}   # tipo → timestamp when blocked
        self.threshold  = threshold
        self.reset_after = reset_after

    def is_open(self, tipo):
        if tipo not in self.blocked_at:
            return False
        if time.time() - self.blocked_at[tipo] > self.reset_after:
            del self.failures[tipo]
            del self.blocked_at[tipo]
            print(f"[CB] ⟳ Circuito restablecido para '{tipo}'")
            return False
        return True

    def record_failure(self, tipo):
        self.failures[tipo] = self.failures.get(tipo, 0) + 1
        if self.failures[tipo] >= self.threshold:
            self.blocked_at[tipo] = time.time()
            print(f"[CB] ✖ Circuito ABIERTO para '{tipo}' ({self.threshold} fallos seguidos) — espera {self.reset_after}s")

    def record_success(self, tipo):
        self.failures.pop(tipo, None)

circuit = CircuitBreaker(threshold=3, reset_after=60)

# ── Heartbeat thread ───────────────────────────────────────────────────────────
_heartbeat_stop = threading.Event()

def _heartbeat_loop(url, headers):
    """Envía ping al servidor cada 20s para que N.O.V.A. sepa que el bot vive."""
    hb_url = f"{url}/api/bot/heartbeat"
    while not _heartbeat_stop.is_set():
        try:
            requests.post(hb_url, headers=headers, json={"status": "alive", "ts": time.time()}, timeout=5)
        except:
            pass  # silencioso — si el servidor no responde, el loop de comandos lo detectará
        _heartbeat_stop.wait(20)

# ── Error reporter ─────────────────────────────────────────────────────────────
def report_error(url, headers, tipo, error_msg):
    """Envía errores al servidor para que N.O.V.A. aprenda de ellos."""
    try:
        requests.post(
            f"{url}/api/bot/error-log",
            headers=headers,
            json={"tipo": tipo, "error": error_msg, "ts": datetime.now().isoformat()},
            timeout=5
        )
    except:
        pass

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

    # Start heartbeat thread
    _heartbeat_stop.clear()
    hb = threading.Thread(target=_heartbeat_loop, args=(url, headers), daemon=True)
    hb.start()

    print(f"\n✓ Bot conectado a {url}")
    print("♥ Heartbeat activo — N.O.V.A. sabrá que estoy en línea")
    print("⛨ Circuit breaker activo — auto-skip de comandos que fallan 3x seguidas")
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

                # Circuit breaker check
                if circuit.is_open(tipo):
                    remaining = int(circuit.reset_after - (time.time() - circuit.blocked_at.get(tipo, 0)))
                    msg = f"Circuito abierto para '{tipo}' — demasiados fallos. Espera {remaining}s o reinicia el bot."
                    print(f"       ⊗ BLOQUEADO: {msg}")
                    try:
                        requests.post(result(cid), headers=headers,
                                      json={"estado": "error", "resultado": {"ok": False, "error": msg}}, timeout=10)
                    except: pass
                    continue

                handler = HANDLERS.get(tipo)
                res     = handler(payload) if handler else {"ok": False, "error": f"Tipo desconocido: {tipo}"}

                # Promote fail-safe errors so the server/AI can stop immediately
                if not res.get("ok") and "fail-safe" in str(res.get("error", "")).lower():
                    res["failsafe"] = True
                    res["error"] = ("⛔ FAILSAFE ACTIVO — el cursor tocó una esquina de la pantalla. "
                                   "Dile a Denison que mueva el mouse al centro y confirme antes de continuar.")

                estado  = "completado" if res.get("ok") else "error"

                # Update circuit breaker
                if res.get("ok"):
                    circuit.record_success(tipo)
                else:
                    circuit.record_failure(tipo)
                    report_error(url, headers, tipo, res.get("error", "unknown"))

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
            _heartbeat_stop.set()
            print("\nBot detenido. ¡Hasta luego!")
            break
        except Exception as e:
            errors += 1
            wait = min(2 ** errors, 30)
            print(f"Error de red ({errors}): {e} — reintentando en {wait}s...")
            time.sleep(wait)
            continue

        time.sleep(2)

# ── Watchdog (auto-reinicio si el bot se cae) ──────────────────────────────────
# Nivel 2: Si run() lanza una excepción inesperada, reinicia con backoff.
def main_with_watchdog(cfg):
    restart_count  = 0
    max_restarts   = 10
    while True:
        try:
            run(cfg)
            break  # salida limpia (Ctrl+C), no reiniciar
        except KeyboardInterrupt:
            print("\nBot detenido por el usuario.")
            break
        except Exception as e:
            restart_count += 1
            if restart_count > max_restarts:
                print(f"✖ Demasiados reinicios ({max_restarts}). Revisa el error y reinicia manualmente.")
                break
            wait = min(5 * restart_count, 60)
            print(f"\n[WATCHDOG] ⚠ El bot se cayó: {e}")
            print(f"[WATCHDOG] Reiniciando en {wait}s... (intento {restart_count}/{max_restarts})")
            time.sleep(wait)
            print(f"[WATCHDOG] ♻ Reiniciando bot...")

if __name__ == "__main__":
    cfg = get_config()
    main_with_watchdog(cfg)
