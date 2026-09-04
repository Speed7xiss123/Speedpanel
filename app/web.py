# app/web.py
import hmac
import logging
import os
import re
import time
import traceback
import unicodedata
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Tuple

from flask import Flask, jsonify, render_template, request
from werkzeug.utils import secure_filename

from app.database import Database, formatar_cpf
from app.importers import EXTENSOES_IGNORADAS, importar_tudo
from app.license import ALLOWED_PAID_DAYS, criar_licenca, validar_licenca

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s :: %(message)s",
)
logger = logging.getLogger("speedpainel")

app = Flask(__name__, template_folder="../templates", static_folder="../static")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-key-change-me")
app.config["JSON_AS_ASCII"] = False
app.config["JSONIFY_PRETTYPRINT_REGULAR"] = False
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB por request
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.config["TEMPLATES_AUTO_RELOAD"] = True

# O token administrativo nunca tem valor padrão. Sem ele, a geração paga pela
# API fica bloqueada; a emissão continua disponível pelo CLI app/gerar_paga.py.
LICENSE_ADMIN_TOKEN = os.environ.get("LICENSE_ADMIN_TOKEN", "").strip()


def _license_key_from_request() -> str:
    """Obtém a chave sem aceitar licença em query string ou cookie."""
    return (request.headers.get("X-License-Key") or "").strip().upper()


def _admin_token_from_request() -> str:
    token = (request.headers.get("X-License-Admin-Token") or "").strip()
    if token:
        return token
    authorization = (request.headers.get("Authorization") or "").strip()
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def _admin_authorized() -> bool:
    token = _admin_token_from_request()
    return bool(LICENSE_ADMIN_TOKEN) and hmac.compare_digest(token, LICENSE_ADMIN_TOKEN)


def require_license(view: Callable) -> Callable:
    """Bloqueia o acesso a dados quando a chave não está válida no servidor."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        chave = _license_key_from_request()
        resultado = validar_licenca(db, chave, registrar_uso=False)
        if not resultado.get("valida"):
            return jsonify({
                "erro": "Licença necessária para acessar este recurso.",
                "codigo": "LICENSE_REQUIRED",
                "motivo": resultado.get("motivo", "Licença inválida"),
            }), 401
        return view(*args, **kwargs)
    return wrapped


@app.after_request
def _no_cache(response):
    """Desativa cache em dev para o front sempre pegar a versão mais recente."""
    if not app.config.get("PRODUCTION", False):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

UPLOAD_DIR = os.path.abspath(
    os.environ.get("UPLOAD_DIR", os.path.join(os.path.dirname(__file__), "..", "databases"))
)
ALLOWED_UPLOAD_EXT = {".json", ".txt", ".csv"}

db = Database()


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _json_error(message: str, status: int = 400) -> tuple:
    response = jsonify({"erro": message})
    response.status_code = status
    return response


def init_app() -> Flask:
    """Inicializa o banco e importa dados se estiver vazio."""
    try:
        stats = db.stats()
    except Exception as exc:
        logger.exception("Falha ao ler stats: %s", exc)
        stats = {"pessoas": 0, "pastebin": 0}

    if stats.get("pessoas", 0) == 0:
        logger.info("Banco vazio. Importando dados...")
        try:
            importar_tudo(db)
        except Exception:
            logger.exception("Falha na importação inicial")
        stats = db.stats()
        logger.info(
            "Importação concluída. %s pessoas, %s pastebins.",
            stats.get("pessoas", 0), stats.get("pastebin", 0),
        )
    return app


# -------------------- Rota principal --------------------
@app.route("/")
def index():
    try:
        stats = db.stats()
    except Exception:
        logger.exception("Falha ao obter stats")
        stats = {"pessoas": 0, "pastebin": 0}
    return render_template(
        "index.html",
        total_pessoas=stats.get("pessoas", 0),
        total_pastebin=stats.get("pastebin", 0),
    )


# -------------------- API: estatísticas --------------------
@app.route("/api/stats")
@require_license
def api_stats():
    try:
        stats = db.stats()
    except Exception as exc:
        logger.exception("Falha em /api/stats")
        return _json_error(f"Erro ao obter estatísticas: {exc}", 500)
    return jsonify({
        "total_json": stats.get("pessoas", 0),
        "total_pastebin": stats.get("pastebin", 0),
        "pessoas": stats.get("pessoas", 0),
        "pastebin": stats.get("pastebin", 0),
    })


# -------------------- API: health --------------------
@app.route("/api/health")
def api_health():
    try:
        db._get_conn()
        return jsonify({"status": "ok", "database": "ok"})
    except Exception as exc:
        return _json_error(str(exc), 500)


# -------------------- Busca --------------------
def _montar_detalhe(pessoa) -> Dict[str, Any]:
    return {
        "cpf": formatar_cpf(pessoa.cpf),
        "nome": pessoa.nome,
        "nome_mae": pessoa.nome_mae,
        "sexo": pessoa.sexo,
        "data_nasc": pessoa.data_nasc,
        "idade": pessoa.idade,
        "renda": pessoa.renda,
        "escolaridade": pessoa.escolaridade,
        "classe_social": pessoa.classe_social,
        "profissao": pessoa.profissao,
        "enderecos": [
            {
                "logradouro": e.logradouro, "numero": e.numero, "bairro": e.bairro,
                "cidade": e.cidade, "uf": e.uf, "cep": e.cep,
            }
            for e in pessoa.enderecos
        ],
        "telefones": [
            {
                "numero": f"({t.ddd}) {t.numero}" if t.ddd else t.numero,
                "whatsapp": t.whatsapp,
                "tipo": t.tipo,
            }
            for t in pessoa.telefones
        ],
        "emails": [e.endereco for e in pessoa.emails],
        "veiculos": [
            {"placa": v.placa, "modelo": v.modelo, "ano": v.ano}
            for v in pessoa.veiculos
        ],
        "parentes": [
            {"nome": p.nome, "grau": p.grau, "idade": p.idade, "cpf": p.cpf}
            for p in pessoa.parentes
        ],
        "empresas": [{"razao": e["razao"], "cnpj": e["cnpj"]} for e in pessoa.empresas],
        "vazamentos": pessoa.vazamentos_count,
        "fotos": pessoa.fotos,
    }


@app.route("/buscar", methods=["POST"])
@require_license
def buscar():
    modo = (request.form.get("modo") or "cpf").strip().lower()
    termo = (request.form.get("termo") or "").strip()

    if not termo:
        return _json_error("Digite um termo para buscar.", 400)
    if len(termo) < 2:
        return _json_error("Termo muito curto (mínimo 2 caracteres).", 400)

    try:
        if modo == "cpf":
            pessoa = db.buscar_por_cpf(termo)
            if pessoa:
                return jsonify({
                    "modo": "cpf",
                    "encontrado": True,
                    "fonte": "SQLite",
                    "dados": _montar_detalhe(pessoa),
                })
            return jsonify({
                "encontrado": False,
                "modo": "cpf",
                "mensagem": "CPF não encontrado no banco.",
            })

        resultados = db.buscar_generico(termo, modo)
        if resultados:
            return jsonify({
                "modo": modo,
                "encontrado": True,
                "resultados": resultados,
                "total": len(resultados),
            })
        return jsonify({
            "encontrado": False,
            "modo": modo,
            "mensagem": "Nenhum resultado encontrado.",
        })
    except Exception as exc:
        logger.exception("Erro em /buscar")
        return _json_error(f"Erro interno: {exc}", 500)


# -------------------- API: licença --------------------
@app.route("/api/validar", methods=["POST"])
def api_validar():
    try:
        data = request.get_json(silent=True) or {}
        chave = (data.get("chave") or "").strip().upper()
        if not chave:
            return jsonify({"valida": False, "motivo": "Chave vazia"}), 400
        if not re.fullmatch(r"[A-Z0-9]{4}(-[A-Z0-9]{4}){3}", chave):
            return jsonify({"valida": False, "motivo": "Formato de chave inválido"}), 400
        resultado = validar_licenca(db, chave, registrar_uso=True)
        status = 200 if resultado.get("valida") else 401
        return jsonify(resultado), status
    except Exception as exc:
        logger.exception("Erro em /api/validar")
        return jsonify({"valida": False, "motivo": f"Erro interno: {exc}"}), 500


@app.route("/api/gerar_gratis", methods=["POST"])
def api_gerar_gratis():
    try:
        lic = criar_licenca(db, usuario="Gratis", gratis=True)
        return jsonify({
            "chave": lic["chave"],
            "validade": lic["validade"],
            "usuario": lic["usuario"],
            "expira": lic["expira"],
            "gratis": True,
        })
    except Exception as exc:
        logger.exception("Erro em /api/gerar_gratis")
        return _json_error(f"Erro ao gerar licença: {exc}", 500)


@app.route("/api/gerar_paga", methods=["POST"])
def api_gerar_paga():
    if not _admin_authorized():
        return jsonify({
            "erro": "Geração paga disponível somente para o administrador.",
            "codigo": "ADMIN_REQUIRED",
        }), 403
    try:
        data = request.get_json(silent=True) or {}
        usuario = (data.get("usuario") or "").strip()
        dias = _safe_int(data.get("dias"), 30)
        if dias not in ALLOWED_PAID_DAYS:
            return jsonify({
                "erro": f"Dias inválidos. Permitidos: {list(ALLOWED_PAID_DAYS)}",
            }), 400
        lic = criar_licenca(db, usuario=usuario, dias=dias, gratis=False)
        return jsonify({
            "chave": lic["chave"],
            "validade": lic["validade"],
            "usuario": lic["usuario"],
            "expira": lic["expira"],
            "gratis": False,
        })
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        logger.exception("Erro em /api/gerar_paga")
        return _json_error(f"Erro ao gerar licença paga: {exc}", 500)


# -------------------- API: upload / listagem / exclusão --------------------
def _slug_filename(name: str) -> str:
    """Sanitiza o nome do arquivo, mantendo acentos removidos e espaços virando underscore."""
    name = (name or "").strip()
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("._-")
    return name or f"upload_{int(time.time())}.dat"


def _ensure_upload_dir() -> str:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    return UPLOAD_DIR


def _format_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n /= 1024
    return f"{n} GB"


def _list_upload_dir() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not os.path.isdir(UPLOAD_DIR):
        return out
    for name in sorted(os.listdir(UPLOAD_DIR)):
        full = os.path.join(UPLOAD_DIR, name)
        if not os.path.isfile(full):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext in EXTENSOES_IGNORADAS and ext != ".db":
            continue
        try:
            size = os.path.getsize(full)
            mtime = os.path.getmtime(full)
        except OSError:
            continue
        out.append({
            "nome": name,
            "tamanho": size,
            "tamanho_h": _format_size(size),
            "modificado": mtime,
            "modificado_h": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime)),
            "ext": ext,
            "suportado": ext in ALLOWED_UPLOAD_EXT,
        })
    return out


@app.route("/api/upload", methods=["POST"])
@require_license
def api_upload():
    """Recebe um ou mais arquivos via multipart/form-data. Salva em databases/."""
    try:
        _ensure_upload_dir()
        files = request.files.getlist("files") or request.files.getlist("file")
        if not files:
            return jsonify({"erro": "Nenhum arquivo enviado. Use o campo 'files' ou 'file'."}), 400

        saved: List[Dict[str, Any]] = []
        errors: List[Dict[str, str]] = []
        for f in files:
            original = f.filename or "arquivo"
            safe = secure_filename(_slug_filename(original))
            if not safe:
                errors.append({"nome": original, "erro": "nome inválido"})
                continue
            ext = os.path.splitext(safe)[1].lower()
            if ext not in ALLOWED_UPLOAD_EXT:
                errors.append({
                    "nome": original,
                    "erro": f"extensão '{ext}' não suportada (use .json, .txt ou .csv)",
                })
                continue
            target = os.path.join(UPLOAD_DIR, safe)
            try:
                f.save(target)
            except OSError as exc:
                logger.exception("Falha salvando %s", safe)
                errors.append({"nome": original, "erro": f"não foi possível salvar: {exc}"})
                continue
            size = os.path.getsize(target)
            saved.append({
                "nome": safe,
                "original": original,
                "tamanho": size,
                "tamanho_h": _format_size(size),
            })

        reimported = None
        if saved:
            try:
                resumo = importar_tudo(db, pasta=UPLOAD_DIR)
                stats = db.stats()
                reimported = {"resumo": resumo, "stats": stats}
            except Exception as exc:
                logger.exception("Reimportação falhou")
                return jsonify({
                    "ok": True,
                    "salvos": saved,
                    "erros": errors,
                    "reimport_erro": str(exc),
                }), 207

        return jsonify({
            "ok": True,
            "salvos": saved,
            "erros": errors,
            "reimport": reimported,
        })
    except Exception as exc:
        logger.exception("Erro em /api/upload")
        return _json_error(f"Erro no upload: {exc}", 500)


@app.route("/api/list", methods=["GET"])
@require_license
def api_list():
    try:
        return jsonify({"arquivos": _list_upload_dir(), "pasta": UPLOAD_DIR})
    except Exception as exc:
        logger.exception("Erro em /api/list")
        return _json_error(str(exc), 500)


@app.route("/api/delete", methods=["POST"])
@require_license
def api_delete():
    try:
        data = request.get_json(silent=True) or {}
        nome = (data.get("nome") or "").strip()
        if not nome:
            return _json_error("nome do arquivo é obrigatório", 400)
        safe = secure_filename(nome)
        if safe != nome or not safe:
            return _json_error("nome inválido", 400)
        full = os.path.join(UPLOAD_DIR, safe)
        real = os.path.realpath(full)
        if not real.startswith(os.path.realpath(UPLOAD_DIR) + os.sep) and real != os.path.realpath(UPLOAD_DIR):
            return _json_error("caminho fora do diretório permitido", 400)
        if not os.path.isfile(real):
            return _json_error("arquivo não encontrado", 404)
        os.remove(real)
        return jsonify({"ok": True, "removido": safe, "arquivos": _list_upload_dir()})
    except Exception as exc:
        logger.exception("Erro em /api/delete")
        return _json_error(str(exc), 500)


# -------------------- Error handlers --------------------
@app.errorhandler(404)
def not_found(_):
    if request.path.startswith("/api/"):
        return jsonify({"erro": "Endpoint não encontrado"}), 404
    return render_template("index.html",
                           total_pessoas=0, total_pastebin=0), 200


@app.errorhandler(500)
def server_error(exc):
    logger.error("500: %s\n%s", exc, traceback.format_exc())
    if request.path.startswith("/api/"):
        return jsonify({"erro": "Erro interno do servidor"}), 500
    return render_template("index.html",
                           total_pessoas=0, total_pastebin=0), 200


# -------------------- Inicialização --------------------
if __name__ == "__main__":
    init_app()
    port = _safe_int(os.environ.get("PORT"), 5000)
    host = os.environ.get("HOST", "0.0.0.0")
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    logger.info("Servidor SpeedPainel em http://%s:%s (debug=%s)", host, port, debug)
    app.run(host=host, port=port, debug=debug, threaded=True)
