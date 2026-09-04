# app/importers.py
import glob
import json
import logging
import os
import re
from typing import List

import requests

from app.database import Database
from app.models import Email, Endereco, Parente, Pessoa, Telefone, Veiculo

logger = logging.getLogger(__name__)

EXTENSOES_IGNORADAS = {
    ".db", ".sqlite", ".sqlite3", ".db3",
    ".tmp", ".bak", ".log", ".cache",
    ".py", ".pyc", ".pyo",
    ".exe", ".dll", ".so", ".dylib",
    ".zip", ".rar", ".7z", ".tar", ".gz",
    ".png", ".jpg", ".jpeg", ".gif", ".ico",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
}

PASTEBIN_LINKS = [
    "https://pastebin.com/raw/20HVDA86",
    "https://pastebin.com/raw/3bEDYFYT",
    "https://pastebin.com/raw/UNZp7SJW",
    "https://pastebin.com/raw/59nZj79K",
    "https://pastebin.com/raw/xcr1jEhH",
    "https://pastebin.com/raw/7AvXm2iP",
    "https://pastebin.com/raw/4aGaymTM",
    "https://pastebin.com/raw/2P9rD5Wd",
    "https://pastebin.com/raw/pXTWeSky",
    "https://pastebin.com/raw/0vyLw3zu",
    "https://pastebin.com/raw/eXVjKT72",
    "https://pastebin.com/raw/uuUtP8dE",
]

REQUEST_TIMEOUT = 20


def _only_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def importar_json(db: Database, arquivo: str) -> bool:
    try:
        with open(arquivo, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Erro ao ler %s: %s", arquivo, exc)
        return False

    cpf = raw.get("cpf", "") if isinstance(raw, dict) else ""
    if not cpf:
        cad = (raw.get("consulta", {}) or {}).get("cadastral", {}) if isinstance(raw, dict) else {}
        cpf = cad.get("cpf", "")
    cpf = _only_digits(cpf)
    if len(cpf) != 11:
        logger.warning("CPF inválido em %s: %s", arquivo, cpf)
        return False

    consulta = (raw.get("consulta", {}) or {}) if isinstance(raw, dict) else {}
    cad = consulta.get("cadastral", {}) or {}

    p = Pessoa(
        cpf=cpf,
        nome=cad.get("nome", ""),
        nome_mae=(cad.get("mae") or {}).get("nome", ""),
        sexo=cad.get("sexo", ""),
        data_nasc=cad.get("data_nasc", ""),
        idade=cad.get("idade", 0) or 0,
        renda=cad.get("renda", ""),
        escolaridade=cad.get("escolaridade", ""),
        classe_social=cad.get("classe_social", ""),
        profissao=cad.get("profissao", ""),
    )

    for e in consulta.get("enderecos", []) or []:
        p.enderecos.append(Endereco(
            logradouro=e.get("endereco", ""),
            numero=str(e.get("numero", "")),
            bairro=e.get("bairro", ""),
            cidade=e.get("cidade", ""),
            uf=e.get("uf", ""),
            cep=e.get("cep", ""),
        ))

    for t in consulta.get("telefones", []) or []:
        p.telefones.append(Telefone(
            numero=t.get("telefone", ""),
            ddd=t.get("ddd", ""),
            tipo=t.get("tipo", 0),
            whatsapp=bool(t.get("flag_whats_app", False)),
        ))

    for e in consulta.get("emails", []) or []:
        p.emails.append(Email(endereco=e.get("email", "")))

    for v in consulta.get("placas", []) or []:
        p.veiculos.append(Veiculo(
            placa=v.get("placa", ""),
            modelo=v.get("modelo", ""),
            ano=v.get("ano_fab", 0) or 0,
        ))

    for par in consulta.get("parentes", []) or []:
        p.parentes.append(Parente(
            nome=par.get("nome", ""),
            grau=par.get("grau", ""),
            cpf=par.get("cpf_parente", ""),
            idade=par.get("idade", 0) or 0,
        ))

    db.inserir_pessoa(p, json.dumps(raw, ensure_ascii=False))
    logger.info("Importado CPF %s de %s", cpf, os.path.basename(arquivo))
    return True


def importar_lista_classificacao(db: Database, arquivo: str) -> int:
    try:
        with open(arquivo, "r", encoding="utf-8-sig") as f:
            linhas = f.readlines()
    except OSError as exc:
        logger.error("Erro ao ler %s: %s", arquivo, exc)
        return 0

    cargo_atual = ""
    count = 0
    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue
        if linha.startswith("CARGO "):
            cargo_atual = linha.replace("CARGO ", "", 1).strip()
            continue
        if "CLASSIFICAÇÃO" in linha or "NOME COMPLETO" in linha:
            continue
        partes = linha.split()
        if len(partes) < 5:
            continue
        cpf = None
        nome_parts: List[str] = []
        data_nasc = None
        pontos = None
        for i, part in enumerate(partes):
            if "." in part and "-" in part and len(_only_digits(part)) == 11:
                cpf = part
                nome_parts = partes[1:i]
                if i + 2 < len(partes):
                    data_nasc = partes[i + 1]
                    pontos = partes[i + 2]
                break
        if not cpf:
            continue
        cpf_limpo = _only_digits(cpf)
        if len(cpf_limpo) != 11:
            continue
        if db.buscar_por_cpf(cpf_limpo):
            continue
        p = Pessoa(cpf=cpf_limpo, nome=" ".join(nome_parts), data_nasc=data_nasc or "")
        raw_info = {"fonte": "lista_classificacao", "cargo": cargo_atual, "pontos": pontos}
        db.inserir_pessoa(p, json.dumps(raw_info, ensure_ascii=False))
        count += 1
    if count:
        logger.info("Lista de classificação: %s novos CPFs de %s", count, os.path.basename(arquivo))
    return count


def importar_cadastros(db: Database, arquivo: str) -> int:
    try:
        with open(arquivo, "r", encoding="utf-8-sig") as f:
            conteudo = f.read()
    except OSError as exc:
        logger.error("Erro ao ler %s: %s", arquivo, exc)
        return 0

    blocos = re.split(r"\n\s*\n|Logo Deixara de ser free", conteudo)
    count = 0
    for bloco in blocos:
        bloco = bloco.strip()
        if not bloco:
            continue
        dados = {}
        for linha in bloco.split("\n"):
            linha = linha.strip()
            if ":" in linha:
                chave, valor = linha.split(":", 1)
                dados[chave.strip().lower()] = valor.strip()
        cpf = _only_digits(dados.get("cpf", ""))
        if len(cpf) != 11 or db.buscar_por_cpf(cpf):
            continue
        p = Pessoa(
            cpf=cpf,
            nome=dados.get("nome", ""),
            nome_mae=dados.get("mae", ""),
            data_nasc=dados.get("data de nascimento", ""),
        )
        if dados.get("rua"):
            p.enderecos.append(Endereco(
                logradouro=dados.get("rua", ""),
                numero=dados.get("numero", ""),
                bairro=dados.get("bairro", ""),
                cidade=dados.get("municipio", ""),
                uf=dados.get("estado", ""),
                cep=dados.get("cep", ""),
            ))
        db.inserir_pessoa(p)
        count += 1
    if count:
        logger.info("Cadastros: %s novos CPFs de %s", count, os.path.basename(arquivo))
    return count


def importar_pastebin(db: Database) -> int:
    """Baixa CPFs dos pastebins configurados. Falhas de rede são toleradas."""
    todos: List[dict] = []
    for url in PASTEBIN_LINKS:
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            resp.encoding = "utf-8"
        except requests.RequestException as exc:
            logger.warning("Falha em %s: %s", url, exc)
            continue
        for linha in resp.text.split("\n"):
            linha = linha.strip()
            if not linha:
                continue
            m = re.search(r"(\d{3}\.\d{3}\.\d{3}-\d{2})", linha)
            if not m:
                continue
            cpf = _only_digits(m.group(1))
            if len(cpf) != 11:
                continue
            nome = linha.split(m.group(1))[0].strip()
            nome = re.sub(r"^\d+\s+", "", nome)
            nome = re.sub(r"^[Nn]ome[:\s]+", "", nome)
            todos.append({"cpf": cpf, "nome": nome, "fonte": url})

    if not todos:
        logger.warning("Nenhum CPF baixado do Pastebin.")
        return 0

    conn = db._get_conn()
    cur = conn.cursor()
    count = 0
    for item in todos:
        try:
            cur.execute(
                "INSERT OR REPLACE INTO pastebin_cpfs (cpf, nome, data_nasc, fonte) VALUES (?,?,?,?)",
                (item["cpf"], item["nome"], "", item["fonte"]),
            )
            count += 1
        except Exception as exc:
            logger.debug("Falha ao inserir %s: %s", item.get("cpf"), exc)
    conn.commit()
    logger.info("Pastebin: %s CPFs importados de %s fontes.", count, len(PASTEBIN_LINKS))
    return count


def importar_lista_simples(db: Database, arquivo: str) -> int:
    try:
        with open(arquivo, "r", encoding="utf-8-sig") as f:
            linhas = f.readlines()
    except OSError as exc:
        logger.error("Erro ao ler %s: %s", arquivo, exc)
        return 0

    count = 0
    for linha in linhas:
        linha = linha.strip()
        if not linha or ":" not in linha:
            continue
        partes = linha.split(":", 1)
        cpf = _only_digits(partes[0].strip())
        data = partes[1].strip()
        if len(cpf) != 11 or db.buscar_por_cpf(cpf):
            continue
        db.inserir_pessoa(Pessoa(cpf=cpf, data_nasc=data))
        count += 1
    if count:
        logger.info("Lista simples: %s novos CPFs de %s", count, os.path.basename(arquivo))
    return count


def importar_tudo(db: Database, pasta: str = "databases") -> dict:
    """Varre a pasta 'databases' e importa todos os arquivos suportados."""
    resultado = {"json": 0, "txt": 0, "pastebin": 0, "arquivos": 0}

    if not os.path.exists(pasta):
        os.makedirs(pasta, exist_ok=True)
        logger.info("Pasta '%s' criada. Coloque seus arquivos de dados lá.", pasta)
        importar_pastebin(db)
        resultado["pastebin"] = 0
        return resultado

    arquivos = glob.glob(os.path.join(pasta, "*.*"))
    arquivos_validos = []
    ignorados = []
    for arq in arquivos:
        ext = os.path.splitext(arq)[1].lower()
        if ext in EXTENSOES_IGNORADAS:
            ignorados.append(os.path.basename(arq))
        else:
            arquivos_validos.append(arq)

    if ignorados:
        logger.info("Arquivos ignorados: %s", ", ".join(ignorados))

    if not arquivos_validos:
        logger.info("Nenhum arquivo válido em '%s'.", pasta)
        resultado["pastebin"] = importar_pastebin(db)
        return resultado

    logger.info("Importando dados de '%s' (%s arquivos)...", pasta, len(arquivos_validos))
    for arquivo in arquivos_validos:
        ext = os.path.splitext(arquivo)[1].lower()
        nome_base = os.path.basename(arquivo)
        resultado["arquivos"] += 1
        try:
            if ext == ".json":
                if importar_json(db, arquivo):
                    resultado["json"] += 1
            elif ext in (".txt", ".csv"):
                try:
                    with open(arquivo, "r", encoding="utf-8-sig", errors="ignore") as f:
                        primeira_linha = f.readline().strip()
                except OSError:
                    continue
                if "CARGO " in primeira_linha or "CLASSIFICAÇÃO" in primeira_linha:
                    importar_lista_classificacao(db, arquivo)
                    resultado["txt"] += 1
                elif "Nome:" in primeira_linha or "CPF:" in primeira_linha:
                    importar_cadastros(db, arquivo)
                    resultado["txt"] += 1
                else:
                    importar_lista_simples(db, arquivo)
                    resultado["txt"] += 1
            else:
                logger.warning("Extensão %s não suportada em %s", ext, nome_base)
        except Exception as exc:
            logger.exception("Falha ao importar %s: %s", nome_base, exc)

    resultado["pastebin"] = importar_pastebin(db)
    return resultado
