# app/database.py
import logging
import sqlite3
import json
import re
import threading
from typing import Optional, List, Dict
from app.models import Pessoa, Endereco, Telefone, Email, Veiculo, Parente

logger = logging.getLogger(__name__)

DB_PATH = "cpf15M.db"


class Database:
    """Camada de acesso a dados SQLite, thread-safe."""

    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._local = threading.local()
        self._lock = threading.Lock()

    def _get_conn(self):
        """Obtém a conexão SQLite para a thread atual (lazy + thread-local)."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
            self._create_tables(conn)
        return conn

    def _table_columns(self, conn: sqlite3.Connection, table: str) -> set:
        try:
            rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
            return {r[1] for r in rows}
        except sqlite3.Error:
            return set()

    def _index_if_column(self, conn: sqlite3.Connection, index: str, table: str, column: str) -> None:
        cols = self._table_columns(conn, table)
        if not cols or column not in cols:
            return
        try:
            conn.execute(f"CREATE INDEX IF NOT EXISTS {index} ON {table}({column})")
        except sqlite3.Error as exc:
            logger.debug("índice %s não criado: %s", index, exc)

    def _safe_create_indexes(self, conn: sqlite3.Connection) -> None:
        self._index_if_column(conn, "idx_nome", "pessoas", "nome")
        self._index_if_column(conn, "idx_nome_mae", "pessoas", "nome_mae")
        self._index_if_column(conn, "idx_telefone", "telefones", "numero")
        self._index_if_column(conn, "idx_email", "emails", "endereco")
        self._index_if_column(conn, "idx_cidade", "enderecos", "cidade")
        conn.commit()

    def _create_tables(self, conn: sqlite3.Connection) -> None:
        cur = conn.cursor()
        try:
            cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS pessoas (
                cpf TEXT PRIMARY KEY,
                nome TEXT,
                nome_mae TEXT,
                sexo TEXT,
                data_nasc TEXT,
                idade INTEGER,
                renda TEXT,
                escolaridade TEXT,
                classe_social TEXT,
                profissao TEXT,
                raw_json TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_nome ON pessoas(nome);
            CREATE INDEX IF NOT EXISTS idx_nome_mae ON pessoas(nome_mae);

            CREATE TABLE IF NOT EXISTS telefones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cpf TEXT,
                numero TEXT,
                ddd TEXT,
                tipo INTEGER,
                whatsapp INTEGER,
                FOREIGN KEY(cpf) REFERENCES pessoas(cpf)
            );
            CREATE INDEX IF NOT EXISTS idx_telefone ON telefones(numero);
            CREATE INDEX IF NOT EXISTS idx_telefones_cpf ON telefones(cpf);

            CREATE TABLE IF NOT EXISTS emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cpf TEXT,
                endereco TEXT,
                FOREIGN KEY(cpf) REFERENCES pessoas(cpf)
            );
            CREATE INDEX IF NOT EXISTS idx_email ON emails(endereco);
            CREATE INDEX IF NOT EXISTS idx_emails_cpf ON emails(cpf);

            CREATE TABLE IF NOT EXISTS enderecos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cpf TEXT,
                logradouro TEXT,
                numero TEXT,
                bairro TEXT,
                cidade TEXT,
                uf TEXT,
                cep TEXT,
                FOREIGN KEY(cpf) REFERENCES pessoas(cpf)
            );
            CREATE INDEX IF NOT EXISTS idx_cidade ON enderecos(cidade);
            CREATE INDEX IF NOT EXISTS idx_enderecos_cpf ON enderecos(cpf);

            CREATE TABLE IF NOT EXISTS pastebin_cpfs (
                cpf TEXT PRIMARY KEY,
                nome TEXT,
                data_nasc TEXT,
                fonte TEXT
            );

            CREATE TABLE IF NOT EXISTS licenses (
                chave TEXT PRIMARY KEY,
                hash TEXT,
                usuario TEXT,
                criado_em TEXT,
                expira_em TEXT,
                dias_validos INTEGER,
                mac_bind TEXT,
                ativa INTEGER DEFAULT 1,
                gratis INTEGER DEFAULT 0,
                usos INTEGER DEFAULT 0
            );
            """
            )
        except sqlite3.OperationalError as exc:
            logger_msg = f"aviso ao criar schema: {exc}"
            print(logger_msg)
        conn.commit()
        self._safe_create_indexes(conn)

    def inserir_pessoa(self, p: Pessoa, raw_json: str = "") -> None:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO pessoas
            (cpf, nome, nome_mae, sexo, data_nasc, idade, renda, escolaridade, classe_social, profissao, raw_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                p.cpf, p.nome, p.nome_mae, p.sexo, p.data_nasc, p.idade,
                p.renda, p.escolaridade, p.classe_social, p.profissao, raw_json,
            ),
        )
        cur.execute("DELETE FROM telefones WHERE cpf=?", (p.cpf,))
        for t in p.telefones:
            cur.execute(
                "INSERT INTO telefones (cpf, numero, ddd, tipo, whatsapp) VALUES (?,?,?,?,?)",
                (p.cpf, t.numero, t.ddd, t.tipo, 1 if t.whatsapp else 0),
            )
        cur.execute("DELETE FROM emails WHERE cpf=?", (p.cpf,))
        for e in p.emails:
            cur.execute("INSERT INTO emails (cpf, endereco) VALUES (?,?)", (p.cpf, e.endereco))
        cur.execute("DELETE FROM enderecos WHERE cpf=?", (p.cpf,))
        for end in p.enderecos:
            cur.execute(
                "INSERT INTO enderecos (cpf, logradouro, numero, bairro, cidade, uf, cep) VALUES (?,?,?,?,?,?,?)",
                (p.cpf, end.logradouro, end.numero, end.bairro, end.cidade, end.uf, end.cep),
            )
        conn.commit()

    def buscar_por_cpf(self, cpf: str) -> Optional[Pessoa]:
        cpf_limpo = re.sub(r"\D", "", cpf or "")
        if len(cpf_limpo) != 11:
            return None
        conn = self._get_conn()
        cur = conn.cursor()
        row = cur.execute("SELECT * FROM pessoas WHERE cpf=?", (cpf_limpo,)).fetchone()
        if not row:
            return None
        p = Pessoa(
            cpf=row["cpf"], nome=row["nome"], nome_mae=row["nome_mae"],
            sexo=row["sexo"], data_nasc=row["data_nasc"], idade=row["idade"],
            renda=row["renda"], escolaridade=row["escolaridade"],
            classe_social=row["classe_social"], profissao=row["profissao"],
        )
        for t in cur.execute("SELECT * FROM telefones WHERE cpf=?", (p.cpf,)):
            p.telefones.append(
                Telefone(numero=t["numero"], ddd=t["ddd"], tipo=t["tipo"], whatsapp=bool(t["whatsapp"]))
            )
        for e in cur.execute("SELECT endereco FROM emails WHERE cpf=?", (p.cpf,)):
            p.emails.append(Email(endereco=e["endereco"]))
        for e in cur.execute(
            "SELECT logradouro, numero, bairro, cidade, uf, cep FROM enderecos WHERE cpf=?",
            (p.cpf,),
        ):
            p.enderecos.append(
                Endereco(
                    logradouro=e["logradouro"], numero=e["numero"], bairro=e["bairro"],
                    cidade=e["cidade"], uf=e["uf"], cep=e["cep"],
                )
            )
        if row["raw_json"]:
            try:
                data = json.loads(row["raw_json"])
                consulta = data.get("consulta", {}) if isinstance(data, dict) else {}
                for v in consulta.get("placas", []) or []:
                    p.veiculos.append(
                        Veiculo(placa=v.get("placa", ""), modelo=v.get("modelo", ""), ano=v.get("ano_fab", 0))
                    )
                for par in consulta.get("parentes", []) or []:
                    p.parentes.append(
                        Parente(
                            nome=par.get("nome", ""), grau=par.get("grau", ""),
                            cpf=par.get("cpf_parente", ""), idade=par.get("idade", 0),
                        )
                    )
                for s in consulta.get("sociedades", []) or []:
                    p.empresas.append({"razao": s.get("razao_social", ""), "cnpj": s.get("cnpj", "")})
                for f in consulta.get("fotos", []) or []:
                    foto = f.get("foto") if isinstance(f, dict) else f
                    if foto:
                        p.fotos.append(foto)
                p.vazamentos_count = len(consulta.get("vazamentos", []) or [])
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        return p

    def buscar_generico(self, termo: str, modo: str, limite: int = 200) -> List[dict]:
        termo_like = f"%{termo}%"
        conn = self._get_conn()
        cur = conn.cursor()
        resultados: List[dict] = []
        try:
            if modo == "nome":
                rows = cur.execute(
                    "SELECT cpf, nome FROM pessoas WHERE nome LIKE ? LIMIT ?",
                    (termo_like, limite),
                )
            elif modo == "telefone":
                termo_num = re.sub(r"\D", "", termo)
                rows = cur.execute(
                    """
                    SELECT DISTINCT p.cpf, p.nome FROM telefones t
                    JOIN pessoas p ON t.cpf = p.cpf
                    WHERE t.numero LIKE ? OR t.ddd LIKE ? LIMIT ?
                    """,
                    (f"%{termo_num}%", termo_like, limite),
                )
            elif modo == "email":
                rows = cur.execute(
                    """
                    SELECT DISTINCT p.cpf, p.nome FROM emails e
                    JOIN pessoas p ON e.cpf = p.cpf
                    WHERE e.endereco LIKE ? LIMIT ?
                    """,
                    (termo_like, limite),
                )
            elif modo == "placa":
                rows = cur.execute(
                    "SELECT cpf, nome FROM pessoas WHERE raw_json LIKE ? LIMIT ?",
                    (f"%{termo.upper()}%", limite),
                )
            elif modo == "tudo":
                rows = cur.execute(
                    """
                    SELECT DISTINCT p.cpf, p.nome FROM pessoas p
                    LEFT JOIN telefones t ON t.cpf = p.cpf
                    LEFT JOIN emails e ON e.cpf = p.cpf
                    LEFT JOIN enderecos en ON en.cpf = p.cpf
                    WHERE p.cpf LIKE ? OR p.nome LIKE ? OR p.nome_mae LIKE ? OR
                          t.numero LIKE ? OR e.endereco LIKE ? OR en.cidade LIKE ? OR en.logradouro LIKE ?
                    LIMIT ?
                    """,
                    (termo_like, termo_like, termo_like, termo_like, termo_like, termo_like, termo_like, limite),
                )
            else:
                return []
            for r in rows:
                resultados.append({"cpf": formatar_cpf(r["cpf"]), "nome": r["nome"] or ""})
        except sqlite3.Error:
            return []
        return resultados

    def stats(self) -> dict:
        conn = self._get_conn()
        cur = conn.cursor()
        try:
            total_pessoas = cur.execute("SELECT COUNT(*) FROM pessoas").fetchone()[0]
        except sqlite3.Error:
            total_pessoas = 0
        try:
            total_pastebin = cur.execute("SELECT COUNT(*) FROM pastebin_cpfs").fetchone()[0]
        except sqlite3.Error:
            total_pastebin = 0
        return {"pessoas": total_pessoas, "pastebin": total_pastebin}

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass
            self._local.conn = None


def formatar_cpf(cpf: str) -> str:
    cpf = re.sub(r"\D", "", cpf or "")
    if len(cpf) == 11:
        return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
    return cpf
