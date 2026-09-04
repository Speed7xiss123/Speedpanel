# SpeedPainel :: terminal

Painel de consulta unificada com interface web em estética de terminal Linux.
Backend Flask + SQLite. Frontend leve em HTML/CSS/JS puros — sem build step.

```
   _____ ____  ____   ___  __  __ ______ _   _ ____   ___   __
  / ____|  _ \/ __ \ / _ \|  \/  |  ____| \ | |  _ \ / _ \ / /
 | (___ | |_) | |  | | | | | \  / | |__  |  \| | | | | | | | |
  \___ \|  _ <| |  | | | | | |\/| |  __| | . ` | | | | | | | |
  ____) | |_) | |__| | |_| | |  | | |____| |\  | |_| | |_| | |
 |_____/|____/ \____/ \___/|_|  |_|______|_| \_|____/ \___/|_|
```

## Recursos

- Busca por **CPF**, **nome**, **telefone**, **email**, **placa** ou **global**.
- Detalhe completo: endereço, telefones, e-mails, veículos, parentes, empresas, vazamentos e fotos.
- Sistema de licença: gratuita (7 dias) e paga (30/60/90 dias), com validação server-side.
- Importadores para JSON, TXT/CSV, listas de classificação e pastebins.
- Interface estilo terminal: prompt, typing effect, scanlines, atalhos de teclado.
- Histórico de buscas (localStorage) com debounce e persistência de sessão.
- API REST: `/api/stats`, `/api/validar`, `/api/gerar_gratis`, `/api/gerar_paga`, `/api/health`.

## Requisitos

- Python **3.10+**
- Pip
- Windows, Linux ou macOS

## Instalação e execução

### Windows

```bat
start.bat
```

### Linux / macOS

```bash
chmod +x start.sh
./start.sh
```

Os scripts criam um `.venv`, instalam as dependências e iniciam o servidor em `http://localhost:5000`.

### Manual

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
python -m app.web
```

## Configuração (variáveis de ambiente)

| Variável | Padrão | Descrição |
|---|---|---|
| `PORT` | `5000` | Porta do servidor |
| `HOST` | `0.0.0.0` | Host de bind |
| `SECRET_KEY` | `dev-key-change-me` | Segredo Flask |
| `FLASK_DEBUG` | `0` | `1` para modo debug |
| `LICENSE_SECRET` | `SPEED7XISS-SECRET-2026` | Assinatura das chaves |
| `LICENSE_DAYS` | `30` | Dias padrão para licenças pagas |
| `LICENSE_FREE_DAYS` | `7` | Dias para licenças gratuitas |
| `LICENSE_ADMIN_TOKEN` | vazio | Token opcional para emissão paga via API; sem ele a rota fica bloqueada |

## Estrutura

```
projeto2/
├── app/
│   ├── database.py     # camada SQLite (thread-safe, índices)
│   ├── importers.py    # importadores de JSON/TXT/pastebin
│   ├── license.py      # geração e validação de chaves
│   ├── models.py       # dataclasses
│   ├── web.py          # rotas Flask + API
│   └── gerar_paga.py   # CLI: gera licença paga avulsa
├── databases/          # coloque aqui seus arquivos de dados
├── static/             # css e js
├── templates/          # index.html
├── cpf15M.db           # banco SQLite (gerado na 1ª execução)
├── requirements.txt
├── start.bat / start.sh
└── README.md
```

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| GET | `/` | Interface web |
| POST | `/buscar` | Consulta por modo+termo |
| GET | `/api/stats` | Total de pessoas e pastebins |
| GET | `/api/health` | Health check |
| POST | `/api/validar` | `{"chave":"XXXX-XXXX-XXXX-XXXX"}` |
| POST | `/api/gerar_gratis` | Cria licença de 7 dias |
| POST | `/api/gerar_paga` | Requer `X-License-Admin-Token`; `{"dias":30,"usuario":"nome"}` (30/60/90) |

## Atalhos do teclado

| Tecla | Ação |
|---|---|
| `Enter` | Executar busca |
| `Esc` | Fechar modal |
| `/` | Focar campo de busca |
| `Ctrl+K` | Abrir modal de licença |
| `Ctrl+L` | Limpar saída |

## CLI: gerar licença paga avulsa

A emissão paga deve ser feita no servidor, fora do navegador. Isso evita deixar um gerador de licenças exposto para qualquer visitante.


```bash
python -m app.gerar_paga
# ou
python -c "from app.database import Database; from app.license import criar_licenca; print(criar_licenca(Database(), usuario='cliente_x', dias=60))"
```

## Notas

- O banco é criado automaticamente na primeira execução se a pasta `databases/` estiver vazia. Os pastebins configurados em `app/importers.py` são baixados nesse momento.
- Todas as consultas via web são executadas em modo `read_only` na thread de origem — `check_same_thread=False` está configurado para evitar travamentos em requisições simultâneas.
- O front mantém apenas a chave em `localStorage` para restauração visual da sessão; cada chamada de dados envia `X-License-Key` e é validada novamente no servidor.
- A rota `/api/health` permanece pública para monitoramento. Busca, estatísticas, upload, listagem e exclusão exigem uma licença válida.
- O endpoint `/api/gerar_paga` exige `LICENSE_ADMIN_TOKEN`; sem essa variável, use o CLI administrativo.
