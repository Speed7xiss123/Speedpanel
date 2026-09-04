import hashlib
import hmac
import logging
import os
import re
import secrets
import string
from datetime import datetime, timedelta
from typing import Optional

from app.database import Database

logger = logging.getLogger(__name__)

# O segredo continua compatível com as licenças já gravadas no SQLite.
SECRET_KEY = os.environ.get("LICENSE_SECRET", "SPEED7XISS-SECRET-2026")
VALIDITY_DAYS = int(os.environ.get("LICENSE_DAYS", "30"))
FREE_VALIDITY_DAYS = int(os.environ.get("LICENSE_FREE_DAYS", "7"))
ALLOWED_PAID_DAYS = (30, 60, 90)
LICENSE_PATTERN = re.compile(r"^[A-Z0-9]{4}(?:-[A-Z0-9]{4}){3}$")


def _gerar_segmento(tamanho: int = 4) -> str:
    """Gera um segmento imprevisível usando o gerador criptográfico do sistema."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(tamanho))


def gerar_chave() -> str:
    """Gera uma chave no formato XXXX-XXXX-XXXX-XXXX."""
    return "-".join(_gerar_segmento() for _ in range(4))


def normalizar_chave(chave: Optional[str]) -> str:
    """Normaliza a entrada sem aceitar caracteres fora do formato público."""
    return re.sub(r"\s+", "", str(chave or "")).upper()


def gerar_hash(chave: str, mac: Optional[str] = None) -> str:
    """Calcula a assinatura compatível com as licenças existentes."""
    payload = f"{normalizar_chave(chave)}{mac or ''}{SECRET_KEY}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _normalizar_dias(dias: Optional[int]) -> int:
    if dias is None:
        return VALIDITY_DAYS
    if dias not in ALLOWED_PAID_DAYS:
        raise ValueError(f"Dias inválidos. Permitidos: {ALLOWED_PAID_DAYS}")
    return dias


def criar_licenca(
    db: Database,
    usuario: str = "",
    dias: Optional[int] = None,
    gratis: bool = False,
) -> dict:
    """Cria e persiste uma licença. Para licença grátis, dias são fixos."""
    try:
        dias_final = FREE_VALIDITY_DAYS if gratis else _normalizar_dias(dias)
        chave = gerar_chave()
        mac_bind = None
        hash_lic = gerar_hash(chave, mac_bind)
        criado_em = datetime.now()
        expira_em = criado_em + timedelta(days=dias_final)
        usuario_final = usuario.strip() or f"Usuario_{_gerar_segmento()}"

        conn = db._get_conn()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO licenses
                (chave, hash, usuario, criado_em, expira_em, dias_validos,
                 mac_bind, ativa, gratis, usos)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                chave,
                hash_lic,
                usuario_final,
                criado_em.isoformat(),
                expira_em.isoformat(),
                dias_final,
                mac_bind,
                1,
                1 if gratis else 0,
                0,
            ),
        )
        conn.commit()
        logger.info("Licença criada: %s (%s, %s dias)", chave, usuario_final, dias_final)
        return {
            "chave": chave,
            "usuario": usuario_final,
            "validade": dias_final,
            "expira": expira_em.isoformat(),
            "gratis": gratis,
            "criado_em": criado_em.isoformat(),
        }
    except Exception as exc:
        logger.exception("Erro ao criar licença")
        raise RuntimeError(f"Falha ao criar licença: {exc}") from exc


def validar_licenca(
    db: Database,
    chave: str,
    mac: Optional[str] = None,
    registrar_uso: bool = True,
) -> dict:
    """Valida uma chave e, opcionalmente, contabiliza o uso."""
    try:
        chave_normalizada = normalizar_chave(chave)
        if not chave_normalizada:
            return {"valida": False, "motivo": "Chave vazia"}
        if not LICENSE_PATTERN.fullmatch(chave_normalizada):
            return {"valida": False, "motivo": "Formato de chave inválido"}

        conn = db._get_conn()
        cur = conn.cursor()
        row = cur.execute("SELECT * FROM licenses WHERE chave=?", (chave_normalizada,)).fetchone()
        if not row:
            return {"valida": False, "motivo": "Chave não encontrada"}
        if not row["ativa"]:
            return {"valida": False, "motivo": "Licença desativada"}

        try:
            expira = datetime.fromisoformat(row["expira_em"])
        except (TypeError, ValueError):
            return {"valida": False, "motivo": "Data de expiração inválida"}
        if datetime.now() > expira:
            return {"valida": False, "motivo": "Licença expirada"}

        mac_cadastrado = row["mac_bind"]
        if mac_cadastrado and mac_cadastrado != (mac or ""):
            return {"valida": False, "motivo": "MAC não autorizado"}

        hash_esperado = gerar_hash(chave_normalizada, mac_cadastrado)
        if not hmac.compare_digest(str(row["hash"] or ""), hash_esperado):
            return {"valida": False, "motivo": "Assinatura inválida"}

        if registrar_uso:
            cur.execute(
                "UPDATE licenses SET usos = COALESCE(usos, 0) + 1 WHERE chave=?",
                (chave_normalizada,),
            )
            conn.commit()

        return {
            "valida": True,
            "ativa": True,
            "chave": chave_normalizada,
            "usuario": row["usuario"],
            "gratis": bool(row["gratis"]),
            "expira": row["expira_em"],
            "dias_validos": row["dias_validos"],
        }
    except Exception as exc:
        logger.exception("Erro ao validar licença")
        return {"valida": False, "motivo": f"Erro interno: {exc}"}
