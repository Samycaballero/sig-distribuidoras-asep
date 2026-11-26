"""Diagnostico gerencial con IA generativa: contexto = KPIs gold + descomposicion LMDI + hallazgos + calidad de datos.
(Adaptado del proyecto anterior: mismos proveedores y la misma politica de caida explicita a plantilla.)

Modos (se elige UNO y se etiqueta con el proveedor realmente usado; nunca se simula otro).
Prioridad automatica: anthropic > gemini > ollama > bedrock > offline
  anthropic : ANTHROPIC_API_KEY -> API de Anthropic (ANTHROPIC_MODEL, defecto claude-haiku-5-5)
  gemini    : GEMINI_API_KEY (o GOOGLE_API_KEY) -> Google Gemini API, nivel gratuito (REST generateContent).
              GEMINI_MODEL fija el modelo; si no, se descubre con GET /models (preferencia flash-lite > flash).
  ollama    : OLLAMA_MODEL (p.ej. llama3.2:3b) -> servidor local Ollama (OLLAMA_HOST, defecto http://localhost:11434).
              Solo se activa si OLLAMA_MODEL esta definido (no se sondea la red).
  bedrock   : BEDROCK_MODEL_ID + credenciales AWS -> Amazon Bedrock (API Converse)
  offline   : plantilla determinista, etiquetada "modo offline (plantilla)"
SIG_LLM=anthropic|gemini|ollama|bedrock|offline fuerza un modo (GENAI_MODE se acepta como alias antiguo).
Si el LLM falla (401/403/429/timeout/sin servidor), se cae a plantilla con WARNING en el log y la etiqueta
offline (no silencioso). Las claves nunca se registran ni van en la URL (Gemini: header x-goog-api-key).
"""
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request

log = logging.getLogger("genai")

ETIQUETA_OFFLINE = "modo offline (plantilla)"
MODELO_ANTHROPIC_DEFECTO = "claude-haiku-5-5"
MODOS = ("anthropic", "gemini", "ollama", "bedrock", "offline")
GEMINI_BASE_DEFECTO = "https://generativelanguage.googleapis.com/v1beta"
# Respaldo si GET /models falla o no lista ninguno: estable y con nivel gratuito segun la pagina de precios de Google.
MODELO_GEMINI_DEFECTO = "gemini-3.5-flash-lite"
OLLAMA_HOST_DEFECTO = "http://localhost:11434"
_dormir = time.sleep  # sustituible en tests

SYSTEM_PROMPT = (
    "Eres analista del mercado electrico de Panama. Redacta en espanol un diagnostico gerencial breve (maximo 6 vinetas "
    "que empiezan con '- ') para la pregunta: en que distribuidora crece mas el consumo y cuanto se explica por mas clientes "
    "o por mayor consumo por cliente. Usa SOLO las cifras del contexto; no inventes causas: si algo es hipotesis, dilo. "
    "Incluye una vineta de riesgo/limitacion de los datos (errores de la fuente, cambios de definicion)."
)


def _clave_gemini(env):
    return env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY")


def seleccionar_modo(env=None) -> str:
    env = os.environ if env is None else env
    forzado = (env.get("SIG_LLM") or env.get("GENAI_MODE") or "").strip().lower()
    if forzado in MODOS:
        return forzado
    if forzado:
        log.warning("SIG_LLM=%r no es valido (%s); se usa seleccion automatica", forzado, "|".join(MODOS))
    if env.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if _clave_gemini(env):
        return "gemini"
    if env.get("OLLAMA_MODEL"):
        return "ollama"
    if env.get("BEDROCK_MODEL_ID") and _hay_credenciales_aws(env):
        return "bedrock"
    return "offline"


def _hay_credenciales_aws(env) -> bool:
    if env.get("AWS_ACCESS_KEY_ID") and env.get("AWS_SECRET_ACCESS_KEY"):
        return True
    try:
        import boto3
        return boto3.Session().get_credentials() is not None
    except Exception:
        return False


# ---------------- contexto (recuperacion desde gold) ----------------
def construir_contexto(summary):
    """Texto de contexto: respuesta, descomposicion acumulada, hallazgos, reclamos y advertencias de calidad."""
    r = summary["respuesta"]
    lineas = [f"Pregunta: {summary['pregunta']}", f"Periodo: {summary['periodo_base']}.", f"Respuesta calculada: {r['texto']}",
              "Descomposicion LMDI acumulada (GWh; efecto clientes / efecto consumo por cliente):"]
    for x in r["descomposicion_acumulada"]:
        lineas.append(f"- {x['distribuidora']} {x['anio_base']}->{x['anio_fin']}: {x['delta_gwh']:+.0f} GWh ({x['crec_ventas_pct']:+.1f} %); "
                      f"clientes {x['efecto_clientes_gwh']:+.0f}; consumo/cliente {x['efecto_consumo_por_cliente_gwh']:+.0f}")
    lineas.append("Hallazgos:")
    lineas += [f"- {h}" for h in summary.get("hallazgos", [])]
    lineas.append("Advertencias de datos:")
    lineas += [f"- {a}" for a in summary.get("advertencias", [])]
    return "\n".join(lineas)


# ---------------- generacion ----------------
def _plantilla(summary):
    r = summary["respuesta"]
    acum = r["descomposicion_acumulada"]
    pts = [f"- {r['texto']}"]
    total = [x for x in acum if x["distribuidora"] == "TOTAL_3"]
    for x in total:
        pts.append(f"- Total de las 3 distribuidoras {x['anio_base']}→{x['anio_fin']}: {x['delta_gwh']:+.0f} GWh; efecto clientes "
                   f"{x['efecto_clientes_gwh']:+.0f} GWh y efecto consumo por cliente {x['efecto_consumo_por_cliente_gwh']:+.0f} GWh.")
    pts += [f"- {h}" for h in summary.get("hallazgos", [])[3:5]]
    pts.append("- Riesgo: " + summary["advertencias"][1])
    return "\n".join(pts)


def _llamar_anthropic(contexto, env):
    import anthropic
    modelo = env.get("ANTHROPIC_MODEL") or MODELO_ANTHROPIC_DEFECTO
    cliente = anthropic.Anthropic(api_key=env["ANTHROPIC_API_KEY"])
    r = cliente.messages.create(model=modelo, max_tokens=700, system=SYSTEM_PROMPT,
                                messages=[{"role": "user", "content": contexto}])
    return "".join(b.text for b in r.content if getattr(b, "type", "") == "text"), modelo


def _llamar_bedrock(contexto, env):
    import boto3
    modelo = env["BEDROCK_MODEL_ID"]
    region = env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION") or "us-east-1"
    cli = boto3.client("bedrock-runtime", region_name=region)
    r = cli.converse(modelId=modelo, system=[{"text": SYSTEM_PROMPT}],
                     messages=[{"role": "user", "content": [{"text": contexto}]}],
                     inferenceConfig={"maxTokens": 700})
    return r["output"]["message"]["content"][0]["text"], modelo


def _enmascarar(texto, env):
    for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        if env.get(k):
            texto = texto.replace(env[k], "***")
    return texto


def _timeout(env, var, defecto):
    try:
        return float(env.get(var) or defecto)
    except ValueError:
        return defecto


def _http_json(url, cuerpo, headers, timeout):
    """JSON <-> JSON con urllib (GET si no hay cuerpo). 1 reintento con espera si 429 (Retry-After, tope 30 s)."""
    datos = None if cuerpo is None else json.dumps(cuerpo).encode("utf-8")
    hdr = {"Content-Type": "application/json", **headers}
    for intento in (1, 2):
        req = urllib.request.Request(url, data=datos, headers=hdr)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detalle = e.read().decode("utf-8", "replace")[:300]
            if e.code == 429 and intento == 1:
                try:
                    espera = min(float(e.headers.get("Retry-After") or 5), 30.0)
                except ValueError:
                    espera = 5.0
                log.warning("HTTP 429 (limite de uso): reintento unico en %.0f s", espera)
                _dormir(espera)
                continue
            raise RuntimeError(f"HTTP {e.code} {e.reason}: {detalle}") from None


def _elegir_modelo_gemini(nombres):
    """De nombres 'models/x' elige el estable mas nuevo: flash-lite primero, luego flash (sin preview/tts/live)."""
    cands = []
    for n in nombres:
        m = re.fullmatch(r"(?:models/)?(gemini-(\d+(?:\.\d+)*)-flash(-lite)?)", n)
        if m:
            cands.append((bool(m.group(3)), tuple(int(x) for x in m.group(2).split(".")), m.group(1)))
    return max(cands)[2] if cands else None


def _llamar_gemini(contexto, env):
    if not _clave_gemini(env):
        raise RuntimeError("falta GEMINI_API_KEY (o GOOGLE_API_KEY)")
    base = (env.get("GEMINI_BASE_URL") or GEMINI_BASE_DEFECTO).rstrip("/")
    hdr = {"x-goog-api-key": _clave_gemini(env)}  # header, no ?key=: la clave no queda en URLs ni logs
    t = _timeout(env, "GEMINI_TIMEOUT", 60)
    modelo = env.get("GEMINI_MODEL")
    if not modelo:
        try:
            lista = _http_json(f"{base}/models?pageSize=200", None, hdr, t)
            modelo = _elegir_modelo_gemini([m["name"] for m in lista.get("models", [])
                                            if "generateContent" in m.get("supportedGenerationMethods", [])])
        except RuntimeError as exc:
            if "HTTP 401" in str(exc) or "HTTP 403" in str(exc):
                raise  # clave invalida: no tiene sentido seguir
        except (OSError, ValueError):
            pass  # sin descubrimiento: se usa el modelo por defecto y la llamada real decide
        modelo = modelo or MODELO_GEMINI_DEFECTO
    r = _http_json(f"{base}/models/{modelo}:generateContent", {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": contexto}]}],
        # margen amplio: los modelos con "thinking" gastan parte del limite razonando
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048}}, hdr, t)
    cand = (r.get("candidates") or [{}])[0]
    texto = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []) if not p.get("thought")).strip()
    if not texto:
        raise RuntimeError(f"respuesta vacia (finishReason={cand.get('finishReason')}, "
                           f"blockReason={r.get('promptFeedback', {}).get('blockReason')})")
    return texto, modelo


def _llamar_ollama(contexto, env):
    host = (env.get("OLLAMA_HOST") or OLLAMA_HOST_DEFECTO).strip().rstrip("/")
    if "://" not in host:
        host = "http://" + host
    modelo = env["OLLAMA_MODEL"]
    r = _http_json(f"{host}/api/chat", {
        "model": modelo, "stream": False,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": contexto}],
        "options": {"temperature": 0.2, "num_predict": 700}}, {}, _timeout(env, "OLLAMA_TIMEOUT", 180))
    texto = (r.get("message") or {}).get("content", "").strip()
    if not texto:
        raise RuntimeError(f"respuesta vacia (done_reason={r.get('done_reason')})")
    return texto, modelo


ETIQUETAS = {"anthropic": "Anthropic API", "gemini": "Google Gemini", "ollama": "Ollama local",
             "bedrock": "Amazon Bedrock"}
LLAMADAS = {"anthropic": _llamar_anthropic, "gemini": _llamar_gemini, "ollama": _llamar_ollama,
            "bedrock": _llamar_bedrock}


def generar_diagnostico_gerencial(summary, env=None):
    """Devuelve {modo, etiqueta, modelo, texto, error}."""
    env = os.environ if env is None else env
    modo = seleccionar_modo(env)
    contexto = construir_contexto(summary)
    res = {"modo": modo, "etiqueta": ETIQUETA_OFFLINE, "modelo": None, "error": None, "caracteres_contexto": len(contexto)}
    if modo != "offline":
        try:
            texto, modelo = LLAMADAS[modo](contexto, env)
            if not texto.strip():
                raise RuntimeError("respuesta vacia")
            res.update(texto=texto.strip(), modelo=modelo, etiqueta=f"{ETIQUETAS[modo]} ({modelo})")
            log.info("Diagnostico generado con %s", res["etiqueta"])
            return res
        except Exception as exc:  # explicito: se informa y se etiqueta la salida como plantilla
            msg = _enmascarar(str(exc) or type(exc).__name__, env)
            log.warning("FALLO LLM (%s): %s -> se usa plantilla offline", modo, msg)
            res.update(modo="offline", error=f"{modo}: {msg}")
    else:
        log.info("IA generativa en %s (sin proveedor configurado; ver SIG_LLM y .env.example)", ETIQUETA_OFFLINE)
    res["texto"] = _plantilla(summary)
    return res


def ejecutar():
    """Lee gold/kpi_summary.json, genera el diagnostico, lo guarda en gold/diagnostico_ia.json y dentro del resumen."""
    import config
    p = config.gold_dir() / "kpi_summary.json"
    summary = json.loads(p.read_text(encoding="utf-8"))
    summary.pop("diagnostico_ia", None)
    d = generar_diagnostico_gerencial(summary)
    (config.gold_dir() / "diagnostico_ia.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    summary["diagnostico_ia"] = d
    p.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"modo": d["modo"], "etiqueta": d["etiqueta"]}
