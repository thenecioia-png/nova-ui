#!/usr/bin/env python3
"""N.O.V.A BOT LOCAL - Agente Ejecutor con Mejora Continua para Denison The Necio
    v5.0 — Memoria Extendida Local, Análisis Continuo, Aprendizaje, Optimización
"""

import sys, os, json, time, base64, platform, subprocess, threading, shlex
from io import BytesIO
from pathlib import Path
from datetime import datetime
from collections import defaultdict

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

# ═══════════════════════════════════════════════════════════════════════════════
# SISTEMA DE MEMORIA LOCAL — persiste entre sesiones en ~/.nova_bot_memory.json
# ═══════════════════════════════════════════════════════════════════════════════
MEMORY_FILE = Path.home() / ".nova_bot_memory.json"

class BotMemory:
    """
    Memoria persistente local del bot.
    Organizada por categorías: errores_aprendidos, estrategias_exitosas,
    patrones_uso, config_detectada, stats_acumulados
    """
    def __init__(self):
        self.data = self._load()

    def _load(self) -> dict:
        try:
            if MEMORY_FILE.exists():
                return json.loads(MEMORY_FILE.read_text())
        except: pass
        return {
            "errores_aprendidos": {},   # tipo → {error, solucion, contador}
            "estrategias_exitosas": {}, # tipo → {mejor_enfoque, tiempo_prom_ms}
            "patrones_uso": {},         # tipo → contador de usos
            "config_detectada": {},     # OS, resolución, etc.
            "stats_acumulados": {       # historial total cross-sesión
                "total_ejecutados": 0,
                "total_ok": 0,
                "total_errores": 0,
                "sesiones": 0,
                "ultima_sesion": None,
            },
        }

    def save(self):
        try:
            MEMORY_FILE.write_text(json.dumps(self.data, indent=2, ensure_ascii=False))
        except: pass

    def record_success(self, tipo: str, tiempo_ms: float):
        """Registra ejecución exitosa y actualiza tiempo promedio."""
        pat = self.data["patrones_uso"]
        pat[tipo] = pat.get(tipo, 0) + 1

        est = self.data["estrategias_exitosas"]
        if tipo not in est:
            est[tipo] = {"usos_ok": 0, "tiempo_prom_ms": 0}
        prev = est[tipo]
        n = prev["usos_ok"]
        prev["tiempo_prom_ms"] = round((prev["tiempo_prom_ms"] * n + tiempo_ms) / (n + 1), 1)
        prev["usos_ok"] = n + 1

        s = self.data["stats_acumulados"]
        s["total_ejecutados"] += 1
        s["total_ok"] += 1

    def record_error(self, tipo: str, error: str):
        """Registra error para no repetirlo."""
        pat = self.data["patrones_uso"]
        pat[tipo] = pat.get(tipo, 0) + 1

        err = self.data["errores_aprendidos"]
        if tipo not in err:
            err[tipo] = {"ultimo_error": "", "contador": 0}
        err[tipo]["ultimo_error"] = str(error)[:300]
        err[tipo]["contador"] += 1

        s = self.data["stats_acumulados"]
        s["total_ejecutados"] += 1
        s["total_errores"] += 1

    def get_top_commands(self, n=5) -> list:
        """Retorna los N comandos más usados."""
        pat = self.data["patrones_uso"]
        return sorted(pat.items(), key=lambda x: x[1], reverse=True)[:n]

    def get_slow_commands(self, threshold_ms=3000) -> list:
        """Retorna comandos más lentos que threshold."""
        est = self.data["estrategias_exitosas"]
        slow = [(t, v["tiempo_prom_ms"]) for t, v in est.items()
                if v["tiempo_prom_ms"] > threshold_ms]
        return sorted(slow, key=lambda x: x[1], reverse=True)

    def get_error_patterns(self) -> list:
        """Retorna comandos con más errores."""
        err = self.data["errores_aprendidos"]
        return sorted(err.items(), key=lambda x: x[1]["contador"], reverse=True)

    def save_config(self, key: str, value):
        """Guarda configuración detectada del PC."""
        self.data["config_detectada"][key] = value
        self.save()

    def start_session(self):
        s = self.data["stats_acumulados"]
        s["sesiones"] += 1
        s["ultima_sesion"] = datetime.now().isoformat()
        self.save()

    def end_session(self, session_ok: int, session_errors: int):
        self.save()
        return self.session_report(session_ok, session_errors)

    def session_report(self, ses_ok: int, ses_errors: int) -> str:
        s = self.data["stats_acumulados"]
        top = self.get_top_commands(3)
        slow = self.get_slow_commands()
        err_pat = self.get_error_patterns()

        lines = [
            f"\n{'═'*58}",
            f"  REPORTE DE SESIÓN — N.O.V.A. BOT v5.0",
            f"{'─'*58}",
            f"  Esta sesión : ✓ {ses_ok} completados  ✗ {ses_errors} errores",
            f"  Historial   : ✓ {s['total_ok']} ok  ✗ {s['total_errores']} errores  ({s['sesiones']} sesiones)",
        ]
        if top:
            lines.append(f"{'─'*58}")
            lines.append("  Comandos más usados:")
            for t, c in top:
                lines.append(f"    {t:<25} {c} veces")
        if slow:
            lines.append(f"{'─'*58}")
            lines.append("  ⚠ Comandos lentos detectados:")
            for t, ms in slow[:3]:
                lines.append(f"    {t:<25} ~{ms:.0f}ms promedio")
            lines.append("  → Considera optimizar estos con run_command async")
        if err_pat:
            lines.append(f"{'─'*58}")
            lines.append("  ✗ Errores frecuentes aprendidos:")
            for t, v in err_pat[:3]:
                lines.append(f"    {t:<25} {v['contador']}x — {v['ultimo_error'][:60]}")
        lines.append(f"{'═'*58}")
        return "\n".join(lines)

memory = BotMemory()

# ═══════════════════════════════════════════════════════════════════════════════
# ANALIZADOR DE PATRONES — detecta automatizaciones posibles
# ═══════════════════════════════════════════════════════════════════════════════
class PatternAnalyzer:
    """
    Detecta secuencias de comandos que se repiten → sugiere automatizaciones.
    Corre análisis cada 25 comandos ejecutados.
    """
    def __init__(self):
        self.recent_sequence = []   # últimos 10 comandos en esta sesión
        self.session_count   = 0

    def record(self, tipo: str):
        self.recent_sequence.append(tipo)
        if len(self.recent_sequence) > 20:
            self.recent_sequence.pop(0)
        self.session_count += 1

        if self.session_count % 25 == 0:
            self.analyze()

    def analyze(self):
        """Detecta si hay una secuencia que aparece 3+ veces seguidas."""
        if len(self.recent_sequence) < 6:
            return
        seq = self.recent_sequence
        for length in range(2, 5):
            for start in range(len(seq) - length * 2):
                sub = seq[start:start+length]
                rest = seq[start+length:]
                if rest[:length] == sub:
                    tip = " → ".join(sub)
                    print(f"\n  💡 PATRÓN DETECTADO: '{tip}' se repite")
                    print(f"     → N.O.V.A. puede automatizar esta secuencia. Pídele que cree un macro.")
                    return

analyzer = PatternAnalyzer()

# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTION STATS (sesión actual)
# ═══════════════════════════════════════════════════════════════════════════════
_stats = {
    "total":   0,
    "ok":      0,
    "errores": 0,
    "start":   None,
}

# ── Config ────────────────────────────────────────────────────────────────────
CONFIG_FILE = Path.home() / ".nova_bot.json"

def get_config():
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

# ── Reporte estructurado ──────────────────────────────────────────────────────
def report_print(tipo, estado, accion, resultado, problema=""):
    ts = datetime.now().strftime("%H:%M:%S")
    icons = {"completado": "✓", "error": "✗", "bloqueado": "⊗", "ejecutando": "▶"}
    colors = {"completado": "\033[92m", "error": "\033[91m", "bloqueado": "\033[93m", "ejecutando": "\033[94m"}
    reset = "\033[0m"
    icon  = icons.get(estado, "·")
    color = colors.get(estado, "")

    print(f"\n[{ts}] {icon} {tipo}")
    print(f"  Estado:    {color}{estado.upper()}{reset}")
    print(f"  Acción:    {accion[:120]}")
    print(f"  Resultado: {str(resultado)[:200]}")
    if problema:
        print(f"  \033[91mProblema:  {str(problema)[:300]}\033[0m")

# ── Verificar resultado ────────────────────────────────────────────────────────
def verify_result(tipo, resultado):
    if not isinstance(resultado, dict):
        return False, "Resultado inválido"
    ok = resultado.get("ok", False)
    if not ok:
        err = str(resultado.get("error", ""))
        if "failsafe" in err.lower() or "fail-safe" in err.lower():
            return False, "⛔ FAILSAFE — mueve el mouse al centro"
        elif "timeout" in err.lower():
            return False, f"⏱ TIMEOUT — considera aumentar timeout"
        elif "no encontrado" in err.lower() or "not found" in err.lower():
            return False, f"🔍 NO ENCONTRADO: {err}"
        elif "permission" in err.lower() or "acceso" in err.lower():
            return False, f"🔒 PERMISOS: {err}"
        return False, err[:300]
    if tipo == "screenshot" and not resultado.get("imagen_b64") and not resultado.get("screenshot_saved"):
        return False, "Screenshot sin imagen capturada"
    return True, ""

# ══════════════════════════════════════════════════════════════════════════════
# COMMAND HANDLERS
# ══════════════════════════════════════════════════════════════════════════════

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
        texto = str(p.get("texto", ""))
        if not texto: return {"ok": False, "error": "texto vacío"}
        pyperclip.copy(texto)
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "v")
        return {"ok": True, "texto": texto[:80]}
    except Exception as e:
        try:
            pyautogui.write(texto, interval=0.04)
            return {"ok": True, "metodo": "write_fallback"}
        except: return {"ok": False, "error": str(e)}

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
        timeout = int(p.get("timeout", 30))
        try:
            args = shlex.split(cmd)
        except ValueError as e:
            return {"ok": False, "error": f"Comando inválido: {e}"}
        if not args: return {"ok": False, "error": "Comando vacío"}
        r = subprocess.run(args, shell=False, capture_output=True, text=True, timeout=timeout)
        salida = r.stdout[:4000] or r.stderr[:2000] or "(sin salida)"
        return {"ok": True, "salida": salida, "stdout": r.stdout[:4000],
                "stderr": r.stderr[:1000], "codigo": r.returncode}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Timeout después de {p.get('timeout', 30)}s"}
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
        return {"ok": True, "contenido": pyperclip.paste()}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_get_screen_info(p):
    try:
        w, h = pyautogui.size()
        x, y = pyautogui.position()
        # Auto-save screen config to local memory
        memory.save_config("resolucion", f"{w}x{h}")
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
                procs.append({"pid": info.get("pid", 0), "nombre": info.get("name", "?"),
                               "cpu_porcentaje": round(info.get("cpu_percent", 0) or 0, 1),
                               "memoria_mb": round(mem_pct * ram_total / 100 / 1024 / 1024, 1)})
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
    try:
        url = str(p.get("url", ""))
        nueva_pestana = bool(p.get("nueva_pestana", False))
        time.sleep(0.2)
        if nueva_pestana:
            pyautogui.hotkey("ctrl", "t")
            time.sleep(0.5)
        pyautogui.hotkey("ctrl", "l")
        time.sleep(0.3)
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        pyperclip.copy(url)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.2)
        pyautogui.press("enter")
        return {"ok": True, "url": url, "nueva_pestana": nueva_pestana}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_foco_ventana(p):
    try:
        titulo  = str(p.get("titulo", "")).lstrip("-")
        sistema = platform.system()
        if sistema == "Windows":
            try:
                ventanas = pyautogui.getWindowsWithTitle(titulo)
                if ventanas:
                    ventanas[0].activate()
                    return {"ok": True, "ventana": ventanas[0].title}
            except: pass
            pyautogui.hotkey("alt", "tab")
            return {"ok": True, "metodo": "alt_tab"}
        else:
            proceso = str(p.get("proceso", ""))
            if proceso:
                subprocess.Popen(["open", "-a", proceso] if sistema == "Darwin" else ["wmctrl", "-a", titulo])
            return {"ok": True}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_cerrar_pestana(p):
    try:
        pyautogui.hotkey("ctrl", "w")
        return {"ok": True}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_tab_siguiente(p):
    try:
        pyautogui.hotkey("ctrl", "tab")
        return {"ok": True}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_recargar_pagina(p):
    try:
        hard = bool(p.get("hard", False))
        pyautogui.hotkey("ctrl", "shift", "r") if hard else pyautogui.hotkey("ctrl", "r")
        return {"ok": True, "hard": hard}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_copiar_url_actual(p):
    try:
        pyautogui.hotkey("ctrl", "l")
        time.sleep(0.3)
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        pyautogui.hotkey("ctrl", "c")
        time.sleep(0.2)
        pyautogui.press("escape")
        return {"ok": True, "url": pyperclip.paste()}
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

# ── Nuevo: leer memoria local del bot ─────────────────────────────────────────
def do_get_bot_memory(p):
    """Retorna la memoria local del bot para que N.O.V.A. pueda verla."""
    try:
        categoria = p.get("categoria", None)
        if categoria:
            data = memory.data.get(categoria, {})
        else:
            data = {k: v for k, v in memory.data.items()}
        return {"ok": True, "memoria": data}
    except Exception as e: return {"ok": False, "error": str(e)}

# ── Nuevo: obtener reporte de rendimiento ─────────────────────────────────────
def do_reporte_rendimiento(p):
    """Genera reporte de rendimiento del bot para N.O.V.A."""
    try:
        top_cmds   = memory.get_top_commands(5)
        slow_cmds  = memory.get_slow_commands(2000)
        err_pats   = memory.get_error_patterns()
        stats      = memory.data["stats_acumulados"]
        total      = stats["total_ejecutados"]
        tasa_ok    = round(stats["total_ok"] / total * 100, 1) if total > 0 else 0
        return {
            "ok": True,
            "total_ejecutados": total,
            "tasa_exito_pct": tasa_ok,
            "sesiones_totales": stats["sesiones"],
            "top_comandos": dict(top_cmds),
            "comandos_lentos": dict(slow_cmds[:5]),
            "patrones_error": {t: v["contador"] for t, v in err_pats[:5]},
            "config_detectada": memory.data["config_detectada"],
        }
    except Exception as e: return {"ok": False, "error": str(e)}

# ── Live vision ───────────────────────────────────────────────────────────────
def _live_capture_loop(fps):
    global _live_vision_active
    delay = max(1.0 / max(fps, 1), 0.05)
    while _live_vision_active:
        try:
            shot = pyautogui.screenshot()
            buf  = BytesIO()
            shot.convert("RGB").save(buf, format="JPEG", quality=35, optimize=True, subsampling=2)
            requests.post(_push_frame_url, json={"frame_b64": base64.b64encode(buf.getvalue()).decode()},
                          headers=_push_frame_headers, timeout=4)
        except: pass
        time.sleep(delay)

def do_iniciar_vision_live(p):
    global _live_vision_active, _live_vision_thread
    fps = min(int(p.get("fps", 8)), 20)
    _live_vision_active = True
    if _live_vision_thread is None or not _live_vision_thread.is_alive():
        _live_vision_thread = threading.Thread(target=_live_capture_loop, args=(fps,), daemon=True)
        _live_vision_thread.start()
    return {"ok": True, "fps": fps}

def do_detener_vision_live(p):
    global _live_vision_active
    _live_vision_active = False
    return {"ok": True}

def do_escanear_red(p):
    try:
        conexiones = []
        for conn in psutil.net_connections(kind="inet"):
            try:
                laddr = f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else "-"
                raddr = f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else "-"
                pid   = conn.pid or 0
                nombre = ""
                if pid:
                    try: nombre = psutil.Process(pid).name()
                    except: pass
                conexiones.append({"local": laddr, "remoto": raddr, "estado": conn.status or "N/A",
                                    "pid": pid, "proceso": nombre})
            except: pass
        conexiones.sort(key=lambda c: c["estado"])
        suspicious = [c for c in conexiones if c["remoto"] != "-" and not c["remoto"].startswith("127.")]
        return {"ok": True, "conexiones": conexiones[:50], "externas": suspicious[:20], "total": len(conexiones)}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_antivirus_scan(p):
    try:
        ruta = Path(p.get("ruta", "."))
        resultados = []
        SOSPECHOSOS = [".exe", ".bat", ".cmd", ".vbs", ".ps1", ".scr", ".pif", ".com",
                       ".dll", ".sys", ".drv", ".msi", ".jar", ".wsf", ".hta"]
        PALABRAS_CLAVE = [b"powershell", b"cmd.exe", b"WScript", b"CreateObject", b"shell.run",
                          b"base64", b"eval(", b"exec(", b"HKEY_", b"RegWrite", b"Download"]
        archivos = list(ruta.rglob("*"))[:200] if ruta.is_dir() else [ruta]
        for arch in archivos:
            if not arch.is_file(): continue
            alertas = []
            if arch.suffix.lower() in SOSPECHOSOS:
                alertas.append(f"extensión sospechosa: {arch.suffix}")
            try:
                if 0 < arch.stat().st_size < 5_000_000:
                    contenido = arch.read_bytes()
                    for kw in PALABRAS_CLAVE:
                        if kw in contenido:
                            alertas.append(f"contiene: {kw.decode(errors='replace')}")
            except: pass
            if alertas:
                resultados.append({"archivo": str(arch), "alertas": alertas})
        return {"ok": True, "archivos_analizados": len(archivos), "amenazas_detectadas": len(resultados),
                "detalle": resultados[:20], "estado": "⚠️ AMENAZAS" if resultados else "✅ Limpio"}
    except Exception as e: return {"ok": False, "error": str(e)}

def do_info_sistema(p):
    try:
        import platform as plat
        cpu_pct = psutil.cpu_percent(interval=1)
        ram     = psutil.virtual_memory()
        disco   = psutil.disk_usage("/")
        info = {
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
        # Auto-save system config
        memory.save_config("os", info["os"])
        memory.save_config("ram_gb", info["ram_total_gb"])
        return info
    except Exception as e: return {"ok": False, "error": str(e)}

HANDLERS = {
    "screenshot":            do_screenshot,
    "mouse_move":            do_mouse_move,
    "mouse_click":           do_mouse_click,
    "mouse_scroll":          do_mouse_scroll,
    "keyboard_type":         do_keyboard_type,
    "keyboard_press":        do_keyboard_press,
    "keyboard_hotkey":       do_keyboard_hotkey,
    "abrir_app":             do_abrir_app,
    "run_command":           do_run_command,
    "copiar_texto":          do_copiar_texto,
    "pegar_texto":           do_pegar_texto,
    "get_clipboard":         do_get_clipboard,
    "get_screen_info":       do_get_screen_info,
    "get_processes":         do_get_processes,
    "abrir_url":             do_abrir_url,
    "navegar_a":             do_navegar_a,
    "foco_ventana":          do_foco_ventana,
    "cerrar_pestana":        do_cerrar_pestana,
    "tab_siguiente":         do_tab_siguiente,
    "recargar_pagina":       do_recargar_pagina,
    "copiar_url_actual":     do_copiar_url_actual,
    "escribir_archivo":      do_escribir_archivo,
    "leer_archivo":          do_leer_archivo,
    "sleep":                 do_sleep,
    "escanear_red":          do_escanear_red,
    "antivirus_scan":        do_antivirus_scan,
    "info_sistema":          do_info_sistema,
    "iniciar_vision_live":   do_iniciar_vision_live,
    "detener_vision_live":   do_detener_vision_live,
    # ── Nuevos: mejora continua ──────────────────────────────────────────────
    "get_bot_memory":        do_get_bot_memory,
    "reporte_rendimiento":   do_reporte_rendimiento,
}

# ── Circuit Breaker ────────────────────────────────────────────────────────────
class CircuitBreaker:
    def __init__(self, threshold=3, reset_after=60):
        self.failures   = {}
        self.blocked_at = {}
        self.threshold  = threshold
        self.reset_after = reset_after

    def is_open(self, tipo):
        if tipo not in self.blocked_at: return False
        if time.time() - self.blocked_at[tipo] > self.reset_after:
            del self.failures[tipo]
            del self.blocked_at[tipo]
            print(f"  [CB] ⟳ '{tipo}' restablecido")
            return False
        return True

    def record_failure(self, tipo):
        self.failures[tipo] = self.failures.get(tipo, 0) + 1
        if self.failures[tipo] >= self.threshold:
            self.blocked_at[tipo] = time.time()
            print(f"  [CB] ✖ '{tipo}' BLOQUEADO — {self.threshold} fallos")

    def record_success(self, tipo):
        self.failures.pop(tipo, None)

circuit = CircuitBreaker()

# ── Heartbeat ─────────────────────────────────────────────────────────────────
_heartbeat_stop = threading.Event()

def _heartbeat_loop(url, headers):
    while not _heartbeat_stop.is_set():
        try:
            requests.post(f"{url}/api/bot/heartbeat", headers=headers,
                          json={"status": "alive", "ts": time.time()}, timeout=5)
        except: pass
        _heartbeat_stop.wait(20)

def report_error_to_server(url, headers, tipo, error_msg):
    try:
        requests.post(f"{url}/api/bot/error-log", headers=headers,
                      json={"tipo": tipo, "error": error_msg, "ts": datetime.now().isoformat()}, timeout=5)
    except: pass

# ── Execute con ciclo completo de mejora continua ─────────────────────────────
def execute_command(cid, tipo, payload, url, req_headers):
    """
    Ciclo completo: Interpretar → Ejecutar (con timer) → Verificar → Reportar
                    → Registrar en memoria → Detectar patrones
    """
    result_url = f"{url}/api/bot/commands/{cid}/resultado"

    handler = HANDLERS.get(tipo)
    if not handler:
        res = {"ok": False, "error": f"Tipo desconocido: '{tipo}'"}
        report_print(tipo, "error", f"Handler '{tipo}' no existe", str(res["error"]))
        try:
            requests.post(result_url, headers=req_headers,
                          json={"estado": "error", "resultado": res}, timeout=10)
        except: pass
        return "error", res

    # ── EJECUTAR con medición de tiempo ────────────────────────────────────
    payload_preview = json.dumps(payload)[:80] if payload else "{}"
    t0 = time.monotonic()
    try:
        res = handler(payload)
    except Exception as e:
        res = {"ok": False, "error": f"Excepción: {str(e)}"}
    tiempo_ms = round((time.monotonic() - t0) * 1000, 1)

    # Promote fail-safe
    if not res.get("ok") and "fail-safe" in str(res.get("error", "")).lower():
        res["failsafe"] = True
        res["error"] = "⛔ FAILSAFE — mueve el mouse al centro y confirma"

    # ── VERIFICAR ──────────────────────────────────────────────────────────
    es_valido, msg_verificacion = verify_result(tipo, res)
    estado = "completado" if es_valido else "error"

    # ── REPORTAR ───────────────────────────────────────────────────────────
    resultado_resumen = {k: v for k, v in res.items() if k != "imagen_b64"}
    resultado_str = json.dumps(resultado_resumen, ensure_ascii=False)[:200]
    time_tag = f"({tiempo_ms}ms)"

    report_print(
        f"{tipo} {time_tag}",
        estado,
        f"{tipo}({payload_preview})",
        resultado_str,
        msg_verificacion if not es_valido else ""
    )

    # ── CICLO DE MEJORA CONTINUA ─────────────────────────────────────────
    # A. Registrar en memoria local
    if es_valido:
        circuit.record_success(tipo)
        memory.record_success(tipo, tiempo_ms)
        _stats["ok"] += 1
    else:
        circuit.record_failure(tipo)
        memory.record_error(tipo, msg_verificacion or res.get("error", ""))
        report_error_to_server(url, req_headers, tipo, msg_verificacion or res.get("error", ""))
        _stats["errores"] += 1

    _stats["total"] += 1

    # B. Detectar patrones de uso
    analyzer.record(tipo)

    # C. Guardar memoria cada 10 comandos
    if _stats["total"] % 10 == 0:
        memory.save()

    # ── ENVIAR RESULTADO ──────────────────────────────────────────────────
    try:
        requests.post(result_url, headers=req_headers,
                      json={"estado": estado, "resultado": res}, timeout=10)
    except Exception as e:
        print(f"  ⚠ Error enviando resultado: {e}")

    return estado, res

# ── Main loop ─────────────────────────────────────────────────────────────────
def run(cfg):
    global _push_frame_url, _push_frame_headers

    url     = cfg["server_url"]
    headers = {"x-bot-api-key": cfg["api_key"], "Content-Type": "application/json"}
    poll    = f"{url}/api/bot/commands/pending"
    errors  = 0

    _push_frame_url     = f"{url}/api/bot/push-frame"
    _push_frame_headers = headers
    _stats["start"]     = datetime.now()

    # Iniciar sesión en memoria
    memory.start_session()

    # Auto-detect OS and save
    memory.save_config("os", f"{platform.system()} {platform.release()}")
    memory.save_config("python_version", sys.version.split()[0])

    # Heartbeat
    _heartbeat_stop.clear()
    hb = threading.Thread(target=_heartbeat_loop, args=(url, headers), daemon=True)
    hb.start()

    # Stats históricos al inicio
    s = memory.data["stats_acumulados"]
    tasa = round(s["total_ok"] / s["total_ejecutados"] * 100, 1) if s["total_ejecutados"] > 0 else 100.0

    print(f"""
╔══════════════════════════════════════════════════════════╗
║     N.O.V.A. BOT v5.0 — Agente con Mejora Continua      ║
╠══════════════════════════════════════════════════════════╣
║  Servidor : {url[:47]:<47} ║
╠══════════════════════════════════════════════════════════╣
║  ✓ Memoria local persistente activa                      ║
║  ✓ Tracking de tiempo por comando                        ║
║  ✓ Detector de patrones (cada 25 cmds)                   ║
║  ✓ Circuit breaker + heartbeat + verificación            ║
╠══════════════════════════════════════════════════════════╣
║  Historial: {s['total_ejecutados']} cmds | {s['sesiones']} sesiones | {tasa}% éxito{' '*max(0, 14-len(str(tasa)))}║
╚══════════════════════════════════════════════════════════╝
Esperando instrucciones... (Ctrl+C para reporte de sesión)
""")

    while True:
        try:
            r = requests.get(poll, headers=headers, timeout=10)
            if r.status_code == 401:
                print("\n⛔ API Key inválida. Genera una nueva en la web y reinicia.")
                time.sleep(30)
                continue
            r.raise_for_status()
            errors = 0

            comandos = r.json().get("comandos", [])
            for cmd in comandos:
                cid, tipo, payload = cmd["id"], cmd["tipo"], cmd.get("payload", {})

                if circuit.is_open(tipo):
                    remaining = int(circuit.reset_after - (time.time() - circuit.blocked_at.get(tipo, 0)))
                    msg = f"Circuito abierto '{tipo}' — espera {remaining}s"
                    report_print(tipo, "bloqueado", f"Intentar '{tipo}'", "Bloqueado", msg)
                    try:
                        requests.post(f"{url}/api/bot/commands/{cid}/resultado", headers=headers,
                                      json={"estado": "error", "resultado": {"ok": False, "error": msg}}, timeout=10)
                    except: pass
                    continue

                execute_command(cid, tipo, payload, url, headers)

            if not comandos:
                time.sleep(2)

        except KeyboardInterrupt:
            uptime = (datetime.now() - _stats["start"]).seconds // 60
            print(f"\n⏹ Sesión terminada. Duración: {uptime} min")
            print(memory.end_session(_stats["ok"], _stats["errores"]))
            _heartbeat_stop.set()
            break
        except requests.exceptions.ConnectionError:
            errors += 1
            wait = min(2 ** errors, 30)
            print(f"\n  ⚠ Sin conexión (intento {errors}) — reintentando en {wait}s...")
            time.sleep(wait)
        except Exception as e:
            errors += 1
            wait = min(2 ** errors, 30)
            print(f"\n  ✗ Error: {e} — reintentando en {wait}s...")
            time.sleep(wait)

if __name__ == "__main__":
    cfg = get_config()
    run(cfg)
