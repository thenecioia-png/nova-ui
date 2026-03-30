#!/usr/bin/env python3
  """N.O.V.A BOT LOCAL - Agente Ejecutor Autónomo para Denison The Necio
     v4.0 — Motor Ejecutor Avanzado, Verificación paso a paso, Reporte estructurado
     
     MODO DE TRABAJO:
     1. Recibir instrucciones de N.O.V.A.
     2. Interpretarlas correctamente
     3. Ejecutar paso a paso con verificación
     4. Reportar estado: Estado / Acción / Resultado / Problemas
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

  # ── Execution stats ────────────────────────────────────────────────────────────
  _stats = {
      "total":    0,
      "ok":       0,
      "errores":  0,
      "session_start": None,
  }

  # ── Config: accept args from command line or ask ──────────────────────────────
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

  # ── Formato de reporte estructurado ──────────────────────────────────────────
  def report_print(tipo: str, estado: str, accion: str, resultado: str, problema: str = ""):
      """Imprime en el formato: Estado / Acción / Resultado / Problemas"""
      ts = datetime.now().strftime("%H:%M:%S")
      sep = "─" * 60
      if estado == "completado":
          icon = "✓"
          estado_fmt = "\033[92mCOMPLETADO\033[0m"  # verde
      elif estado == "error":
          icon = "✗"
          estado_fmt = "\033[91mERROR\033[0m"  # rojo
      elif estado == "bloqueado":
          icon = "⊗"
          estado_fmt = "\033[93mBLOQUEADO\033[0m"  # amarillo
      else:
          icon = "▶"
          estado_fmt = "\033[94mEJECUTANDO\033[0m"  # azul

      print(f"\n[{ts}] {icon} {tipo}")
      print(f"  Estado:   {estado_fmt}")
      print(f"  Acción:   {accion}")
      print(f"  Resultado: {resultado[:200] if resultado else 'N/A'}")
      if problema:
          print(f"  \033[91mProblema:  {problema[:300]}\033[0m")

  # ── Verificar resultado antes de continuar ───────────────────────────────────
  def verify_result(tipo: str, resultado: dict) -> tuple[bool, str]:
      """
      Verifica si el resultado es válido y da feedback claro.
      Retorna (es_valido, mensaje)
      """
      if not isinstance(resultado, dict):
          return False, "Resultado no es un objeto válido"
      
      ok = resultado.get("ok", False)
      error = resultado.get("error", "")
      
      if not ok:
          # Clasificar tipo de error para dar feedback útil
          err_lower = str(error).lower()
          if "failsafe" in err_lower or "fail-safe" in err_lower:
              return False, f"⛔ FAILSAFE: cursor en esquina — Denison debe mover el mouse al centro"
          elif "timeout" in err_lower:
              return False, f"⏱ TIMEOUT: comando tardó demasiado — considera aumentar el timeout"
          elif "no encontrado" in err_lower or "not found" in err_lower:
              return False, f"🔍 NO ENCONTRADO: {error}"
          elif "permiso" in err_lower or "permission" in err_lower or "access" in err_lower:
              return False, f"🔒 PERMISOS: {error}"
          else:
              return False, str(error)[:300]
      
      # Verificaciones específicas por tipo de comando
      if tipo == "screenshot":
          if not resultado.get("imagen_b64") and not resultado.get("screenshot_saved"):
              return False, "Screenshot ejecutado pero sin imagen capturada"
      elif tipo == "run_command":
          codigo = resultado.get("codigo", 0)
          if codigo not in (0, None) and codigo != 0:
              stderr = resultado.get("stderr", "")
              if stderr and len(stderr) > 5:
                  return True, f"Advertencia: código de salida {codigo}"  # no es error fatal
      elif tipo == "keyboard_type":
          if not resultado.get("texto"):
              return False, "No se especificó texto para escribir"
      
      return True, ""

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
          pyperclip.copy(texto)
          time.sleep(0.05)
          pyautogui.hotkey("ctrl", "v")
          return {"ok": True, "texto": texto[:80]}
      except Exception as e:
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
          timeout = int(p.get("timeout", 30))
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
              "salida": salida,
              "stdout": r.stdout[:4000],
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
      """Navega el tab activo a una URL usando Ctrl+L (sin depender de coordenadas)."""
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
      """Trae al frente una ventana por su título o proceso."""
      try:
          titulo = str(p.get("titulo", "")).lstrip("-")
          proceso = str(p.get("proceso", "")).lstrip("-")
          sistema = platform.system()
          if sistema == "Windows":
              try:
                  ventanas = pyautogui.getWindowsWithTitle(titulo)
                  if ventanas:
                      ventanas[0].activate()
                      return {"ok": True, "ventana": ventanas[0].title}
              except Exception:
                  pass
              pyautogui.hotkey("alt", "tab")
              return {"ok": True, "metodo": "alt_tab"}
          else:
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
          if hard:
              pyautogui.hotkey("ctrl", "shift", "r")
          else:
              pyautogui.hotkey("ctrl", "r")
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
      "navegar_a":        do_navegar_a,
      "foco_ventana":     do_foco_ventana,
      "cerrar_pestana":   do_cerrar_pestana,
      "tab_siguiente":    do_tab_siguiente,
      "recargar_pagina":  do_recargar_pagina,
      "copiar_url_actual": do_copiar_url_actual,
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
      """Evita ejecutar comandos que fallan repetido — auto-reparación Nivel 1."""
      def __init__(self, threshold=3, reset_after=60):
          self.failures   = {}
          self.blocked_at = {}
          self.threshold  = threshold
          self.reset_after = reset_after

      def is_open(self, tipo):
          if tipo not in self.blocked_at:
              return False
          if time.time() - self.blocked_at[tipo] > self.reset_after:
              del self.failures[tipo]
              del self.blocked_at[tipo]
              print(f"  [CB] ⟳ Circuito restablecido para '{tipo}'")
              return False
          return True

      def record_failure(self, tipo):
          self.failures[tipo] = self.failures.get(tipo, 0) + 1
          if self.failures[tipo] >= self.threshold:
              self.blocked_at[tipo] = time.time()
              print(f"  [CB] ✖ Circuito ABIERTO para '{tipo}' — {self.threshold} fallos seguidos, espera {self.reset_after}s")

      def record_success(self, tipo):
          self.failures.pop(tipo, None)

  circuit = CircuitBreaker(threshold=3, reset_after=60)

  # ── Heartbeat thread ───────────────────────────────────────────────────────────
  _heartbeat_stop = threading.Event()

  def _heartbeat_loop(url, headers):
      hb_url = f"{url}/api/bot/heartbeat"
      while not _heartbeat_stop.is_set():
          try:
              requests.post(hb_url, headers=headers, json={"status": "alive", "ts": time.time()}, timeout=5)
          except:
              pass
          _heartbeat_stop.wait(20)

  # ── Error reporter ─────────────────────────────────────────────────────────────
  def report_error(url, headers, tipo, error_msg):
      try:
          requests.post(
              f"{url}/api/bot/error-log",
              headers=headers,
              json={"tipo": tipo, "error": error_msg, "ts": datetime.now().isoformat()},
              timeout=5
          )
      except:
          pass

  # ── Execute a single command with full verification cycle ─────────────────────
  def execute_command(cid: int, tipo: str, payload: dict, url: str, req_headers: dict):
      """
      Ciclo completo: Interpretar → Ejecutar → Verificar → Reportar
      Retorna (estado, resultado)
      """
      result_url = f"{url}/api/bot/commands/{cid}/resultado"

      # ── 1. INTERPRETAR ─────────────────────────────────────────────────────
      handler = HANDLERS.get(tipo)
      if not handler:
          res = {"ok": False, "error": f"Tipo desconocido: '{tipo}' — no existe en los handlers"}
          report_print(tipo, "error",
                       f"Buscando handler para '{tipo}'",
                       "Handler no encontrado",
                       res["error"])
          try:
              requests.post(result_url, headers=req_headers,
                            json={"estado": "error", "resultado": res}, timeout=10)
          except: pass
          return "error", res

      # ── 2. EJECUTAR ────────────────────────────────────────────────────────
      payload_preview = json.dumps(payload)[:80] if payload else "{}"
      report_print(tipo, "ejecutando",
                   f"{tipo}({payload_preview})",
                   "En progreso...")

      try:
          res = handler(payload)
      except Exception as e:
          res = {"ok": False, "error": f"Excepción no capturada: {str(e)}"}

      # ── 3. VERIFICAR ───────────────────────────────────────────────────────
      # Promote fail-safe errors
      if not res.get("ok") and "fail-safe" in str(res.get("error", "")).lower():
          res["failsafe"] = True
          res["error"] = ("⛔ FAILSAFE ACTIVO — el cursor tocó una esquina. "
                         "Mueve el mouse al centro de la pantalla y confirma.")

      es_valido, msg_verificacion = verify_result(tipo, res)
      estado = "completado" if es_valido else "error"

      # ── 4. REPORTAR ────────────────────────────────────────────────────────
      # Build clean summary of result (without base64 blobs)
      resultado_resumen = {k: v for k, v in res.items() if k != "imagen_b64"}
      resultado_str = json.dumps(resultado_resumen, ensure_ascii=False)[:200]

      report_print(
          tipo,
          estado,
          f"{tipo} con payload: {payload_preview}",
          resultado_str,
          msg_verificacion if not es_valido else ""
      )

      # Update circuit breaker
      if es_valido:
          circuit.record_success(tipo)
          _stats["ok"] += 1
      else:
          circuit.record_failure(tipo)
          _stats["errores"] += 1
          report_error(url, req_headers, tipo, msg_verificacion or res.get("error", "unknown"))

      _stats["total"] += 1

      # Send result to server
      try:
          requests.post(result_url, headers=req_headers,
                        json={"estado": estado, "resultado": res}, timeout=10)
      except Exception as e:
          print(f"  ⚠ No se pudo enviar resultado al servidor: {e}")

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
      _stats["session_start"] = datetime.now()

      # Start heartbeat thread
      _heartbeat_stop.clear()
      hb = threading.Thread(target=_heartbeat_loop, args=(url, headers), daemon=True)
      hb.start()

      print(f"""
  ╔══════════════════════════════════════════════════════╗
  ║       N.O.V.A BOT v4.0 — Agente Ejecutor Autónomo   ║
  ╠══════════════════════════════════════════════════════╣
  ║  Servidor : {url[:45]:<45} ║
  ║  Modo     : Ejecución paso a paso con verificación   ║
  ║  Reporte  : Estado / Acción / Resultado / Problemas  ║
  ╠══════════════════════════════════════════════════════╣
  ║  ✓ Heartbeat activo (cada 20s)                       ║
  ║  ✓ Circuit breaker activo (3 fallos = bloqueo)       ║
  ║  ✓ Verificación de resultado en cada comando         ║
  ║  ✓ Reporte automático de errores a N.O.V.A.          ║
  ╚══════════════════════════════════════════════════════╝
  Esperando instrucciones de N.O.V.A... (Ctrl+C para detener)
  """)

      while True:
          try:
              r = requests.get(poll, headers=headers, timeout=10)
              if r.status_code == 401:
                  print("\n⛔ ERROR: API Key inválida. Genera una nueva key en la web y reinicia el bot.")
                  time.sleep(30)
                  continue
              r.raise_for_status()
              errors = 0

              comandos = r.json().get("comandos", [])

              for cmd in comandos:
                  cid     = cmd["id"]
                  tipo    = cmd["tipo"]
                  payload = cmd.get("payload", {})

                  # ── Circuit breaker check ──────────────────────────────────
                  if circuit.is_open(tipo):
                      remaining = int(circuit.reset_after - (time.time() - circuit.blocked_at.get(tipo, 0)))
                      msg = f"Circuito abierto — demasiados fallos en '{tipo}'. Espera {remaining}s o reinicia."
                      report_print(tipo, "bloqueado",
                                   f"Intentar ejecutar '{tipo}'",
                                   "Bloqueado por circuit breaker",
                                   msg)
                      try:
                          requests.post(f"{url}/api/bot/commands/{cid}/resultado",
                                        headers=headers,
                                        json={"estado": "error", "resultado": {"ok": False, "error": msg}},
                                        timeout=10)
                      except: pass
                      continue

                  # ── Execute with full verification cycle ───────────────────
                  execute_command(cid, tipo, payload, url, headers)

          except KeyboardInterrupt:
              print("\n\n⏹ Bot detenido por Denison.")
              uptime = (datetime.now() - _stats["session_start"]).seconds // 60
              print(f"   Sesión: {uptime} min | Total: {_stats['total']} | ✓ {_stats['ok']} | ✗ {_stats['errores']}")
              _heartbeat_stop.set()
              break
          except requests.exceptions.ConnectionError:
              errors += 1
              wait = min(2 ** errors, 30)
              print(f"\n  ⚠ Sin conexión al servidor (intento {errors}) — reintentando en {wait}s...")
              time.sleep(wait)
          except Exception as e:
              errors += 1
              wait = min(2 ** errors, 30)
              print(f"\n  ✗ Error inesperado: {e} — reintentando en {wait}s...")
              time.sleep(wait)
          else:
              if not comandos:
                  time.sleep(2)  # poll cada 2s cuando no hay comandos

  if __name__ == "__main__":
      cfg = get_config()
      run(cfg)
  