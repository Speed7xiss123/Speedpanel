/* =============================================================================
   SpeedPainel v2.1 :: terminal premium
   ============================================================================= */

(function () {
    'use strict';

    // -------------------------------------------------------------------------
    // State
    // -------------------------------------------------------------------------
    const state = {
        tab: 'search',
        modo: 'cpf',
        license: { ativa: false, gratis: true, usuario: '', chave: '', expira: '' },
        authenticated: false,
        history: [],
        requestSeq: 0,
        bootTime: Date.now(),
        modalTrigger: null,
        modalBodyOverflow: '',
    };

    const STORAGE_HISTORY = 'sp_history_v2';
    const STORAGE_LICENSE = { chave: 'sp_license_key_v2', usuario: 'sp_license_user_v2', gratis: 'sp_license_free_v2', expira: 'sp_license_expire_v2' };
    const HISTORY_LIMIT = 12;
    const PLACEHOLDERS = {
        cpf: '012.345.678-90',
        nome: 'isabela',
        telefone: '999156848',
        email: 'email@dominio.com',
        placa: 'KXB5376',
        tudo: 'joao',
    };
    const MODE_LABELS = {
        cpf: 'CPF',
        nome: 'Nome',
        telefone: 'Telefone',
        email: 'E-mail',
        placa: 'Placa',
        tudo: 'Tudo',
    };

    // -------------------------------------------------------------------------
    // DOM helpers
    // -------------------------------------------------------------------------
    const $ = (s) => document.querySelector(s);
    const $$ = (s) => Array.from(document.querySelectorAll(s));
    const el = (tag, props = {}, ...children) => {
        const node = document.createElement(tag);
        Object.entries(props || {}).forEach(([k, v]) => {
            if (v == null || v === false) return;
            if (k === 'class') node.className = v;
            else if (k === 'dataset') Object.assign(node.dataset, v);
            else if (k === 'style' && typeof v === 'object') Object.assign(node.style, v);
            else if (k === 'html') node.innerHTML = v;
            else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2).toLowerCase(), v);
            else if (k in node) node[k] = v;
            else node.setAttribute(k, v);
        });
        children.flat().forEach((c) => {
            if (c == null || c === false) return;
            node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
        });
        return node;
    };
    const escapeHtml = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
    const formatCpf = (cpf) => {
        const d = String(cpf || '').replace(/\D/g, '');
        if (d.length !== 11) return cpf || '—';
        return `${d.slice(0,3)}.${d.slice(3,6)}.${d.slice(6,9)}-${d.slice(9)}`;
    };
    const formatDate = (iso) => {
        if (!iso) return '—';
        try {
            const d = new Date(iso);
            if (isNaN(d.getTime())) return '—';
            return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
        } catch { return '—'; }
    };

    // -------------------------------------------------------------------------
    // UI helpers
    // -------------------------------------------------------------------------
    function setLiveMessage(message, priority = 'polite') {
        const live = $('#liveRegion');
        if (!live) return;
        live.setAttribute('aria-live', priority);
        live.textContent = '';
        window.requestAnimationFrame(() => { live.textContent = message; });
    }

    function setOutputState(message) {
        const stateNode = $('#outputState');
        if (stateNode) stateNode.textContent = message;
    }

    function setButtonBusy(button, busy, busyLabel = 'Aguarde…') {
        if (!button) return;
        const label = button.querySelector('.lbl');
        if (busy) {
            if (!button.dataset.idleContent) button.dataset.idleContent = button.innerHTML;
            if (!button.dataset.idleLabel && label) button.dataset.idleLabel = label.textContent;
            button.disabled = true;
            button.setAttribute('aria-busy', 'true');
            if (label) label.textContent = busyLabel;
            else button.textContent = busyLabel;
        } else {
            button.disabled = false;
            button.removeAttribute('aria-busy');
            if (label && button.dataset.idleLabel) label.textContent = button.dataset.idleLabel;
            else if (button.dataset.idleContent) button.innerHTML = button.dataset.idleContent;
        }
    }

    function licenseHeaders(extra = {}) {
        const headers = { ...extra };
        if (state.license?.chave) headers['X-License-Key'] = state.license.chave;
        return headers;
    }

    async function fetchWithLicense(url, options = {}) {
        const response = await fetch(url, { ...options, headers: licenseHeaders(options.headers || {}) });
        if (response.status === 401 && state.authenticated) {
            let payload = {};
            try { payload = await response.clone().json(); } catch { /* resposta não JSON */ }
            if (payload.codigo === 'LICENSE_REQUIRED') {
                lockAccess(payload.motivo || 'A licença não está mais ativa.');
            }
        }
        return response;
    }

    function updateTabFocus(activeIndex) {
        $$('.tab').forEach((tab, index) => {
            tab.tabIndex = index === activeIndex ? 0 : -1;
        });
    }

    function focusableIn(container) {
        return Array.from(container.querySelectorAll(
            'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'
        ));
    }

    function ensureLiveRegion() {
        let live = $('#liveRegion');
        if (live) return live;
        live = el('div', {
            id: 'liveRegion',
            class: 'sr-only',
            'aria-live': 'polite',
            'aria-atomic': 'true',
        });
        document.body.appendChild(live);
        return live;
    }

    // -------------------------------------------------------------------------
    // Toast
    // -------------------------------------------------------------------------
    function toast(message, kind = 'info', title) {
        const c = $('#toastContainer');
        if (!c) return;
        const titles = { ok: 'sucesso', err: 'erro', warn: 'atenção', info: 'info' };
        const priority = kind === 'err' ? 'assertive' : 'polite';
        const t = el('div', {
            class: `toast ${kind}`,
            role: kind === 'err' ? 'alert' : 'status',
            tabindex: '0',
        },
            el('div', { class: 'toast-content' },
                el('span', { class: 'title' }, title || titles[kind] || 'info'),
                el('span', { class: 'message' }, message),
            ),
            el('button', {
                class: 'toast-close',
                type: 'button',
                'aria-label': 'Fechar notificação',
                onclick: () => t.remove(),
            }, '×'),
        );
        c.appendChild(t);
        setLiveMessage(`${title || titles[kind] || 'info'}: ${message}`, priority);
        const duration = kind === 'err' ? 8000 : 5000;
        let remaining = duration;
        let startedAt = Date.now();
        let paused = false;
        let dismissTimer = window.setTimeout(remove, remaining);
        function remove() { if (t.parentNode) t.remove(); }
        function pause(event) {
            if (paused || (event.relatedTarget && t.contains(event.relatedTarget))) return;
            paused = true;
            remaining = Math.max(0, remaining - (Date.now() - startedAt));
            window.clearTimeout(dismissTimer);
        }
        function resume(event) {
            if (!paused || (event.relatedTarget && t.contains(event.relatedTarget))) return;
            if (!t.parentNode || remaining <= 0) return;
            paused = false;
            startedAt = Date.now();
            dismissTimer = window.setTimeout(remove, remaining);
        }
        t.addEventListener('mouseenter', pause);
        t.addEventListener('mouseleave', resume);
        t.addEventListener('focusin', pause);
        t.addEventListener('focusout', resume);
    }

    // -------------------------------------------------------------------------
    // Tabs (top-level)
    // -------------------------------------------------------------------------
    function switchTab(name, { focusTab = false } = {}) {
        const tab = $(`.tab[data-tab="${name}"]`);
        if (!tab) return;
        state.tab = name;
        $$('.tab').forEach((b) => {
            const on = b === tab;
            b.classList.toggle('active', on);
            b.setAttribute('aria-selected', on ? 'true' : 'false');
        });
        $$('.panel').forEach((p) => {
            const on = p.id === `panel-${name}`;
            p.hidden = !on;
            p.classList.toggle('active', on);
            p.setAttribute('aria-hidden', on ? 'false' : 'true');
        });
        updateTabFocus(Array.from($$('.tab')).indexOf(tab));
        if (name === 'upload') loadFileList();
        if (focusTab) tab.focus();
        setLiveMessage(`${tab.textContent.trim()} selecionada`, 'polite');
    }
    function bindTabs() {
        const tabs = $$('.tab');
        tabs.forEach((b, index) => {
            b.addEventListener('click', () => switchTab(b.dataset.tab));
            b.addEventListener('keydown', (e) => {
                if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
                e.preventDefault();
                let nextIndex = index;
                if (e.key === 'ArrowRight') nextIndex = (index + 1) % tabs.length;
                if (e.key === 'ArrowLeft') nextIndex = (index - 1 + tabs.length) % tabs.length;
                if (e.key === 'Home') nextIndex = 0;
                if (e.key === 'End') nextIndex = tabs.length - 1;
                switchTab(tabs[nextIndex].dataset.tab, { focusTab: true });
            });
        });
        updateTabFocus(Math.max(0, tabs.findIndex((tab) => tab.classList.contains('active'))));
    }

    // -------------------------------------------------------------------------
    // Status / License
    // -------------------------------------------------------------------------
    function applyStatus(license) {
        const card = $('#statusCard');
        const chip = $('#licChip');
        if (!card || !chip) return;
        let s = 'inactive';
        if (license && license.ativa) s = license.gratis ? 'free' : 'active';
        card.dataset.state = s;
        chip.dataset.state = s;
        const setText = (id, v) => { const n = $(id); if (n) n.textContent = v; };
        setText('#statusVal', s === 'inactive' ? 'inativo' : (s === 'free' ? 'free' : 'ativo'));
        setText('#statusUser', license && license.usuario ? license.usuario : '—');
        setText('#statusExpire', license && license.expira ? formatDate(license.expira) : '—');
        setText('#statusType', s === 'active' ? 'PREMIUM' : s === 'free' ? 'FREE' : '—');
        setText('#licVal', s === 'inactive' ? 'inativo' : (s === 'free' ? 'free trial' : 'premium'));
        chip.setAttribute('aria-label', `Status da licença: ${s === 'inactive' ? 'inativa' : s === 'free' ? 'período gratuito' : 'premium'}`);
    }

    function setLoginMessage(text, kind = 'info') {
        const message = $('#loginMessage');
        if (!message) return;
        message.textContent = text;
        message.classList.remove('ok', 'err', 'info');
        message.classList.add(kind);
        message.setAttribute('role', kind === 'err' ? 'alert' : 'status');
        message.setAttribute('aria-live', kind === 'err' ? 'assertive' : 'polite');
    }

    function setAccess(allowed) {
        state.authenticated = !!allowed;
        const gate = $('#loginGate');
        const app = $('#app');
        document.body.classList.toggle('is-authenticated', state.authenticated);
        if (gate) {
            gate.hidden = state.authenticated;
            gate.setAttribute('aria-hidden', state.authenticated ? 'true' : 'false');
        }
        if (app) {
            app.hidden = !state.authenticated;
            app.setAttribute('aria-hidden', state.authenticated ? 'false' : 'true');
        }
        if (state.authenticated) {
            setLoginMessage('Acesso liberado.', 'ok');
            setLiveMessage(`Acesso liberado para ${state.license.usuario || 'usuário'}.`, 'polite');
        } else {
            setLoginMessage('Informe uma chave de licença para continuar.', 'info');
        }
    }

    function lockAccess(message = 'Sua licença não está ativa.') {
        applyLicense({ ativa: false, gratis: true, usuario: '', chave: '', expira: '' });
        setAccess(false);
        setLoginMessage(message, 'err');
        window.setTimeout(() => $('#loginLicenseKey')?.focus(), 60);
    }

    function unlockAccess(license) {
        applyLicense(license);
        setAccess(true);
    }

    function logout() {
        lockAccess('Sessão encerrada. Informe uma licença para entrar novamente.');
        toast('Você saiu do painel.', 'info', 'Sessão encerrada');
    }

    function applyLicense(lic) {
        state.license = lic || { ativa: false, gratis: true, usuario: '', chave: '', expira: '' };
        try {
            if (state.license.ativa) {
                localStorage.setItem(STORAGE_LICENSE.chave, state.license.chave);
                localStorage.setItem(STORAGE_LICENSE.usuario, state.license.usuario);
                localStorage.setItem(STORAGE_LICENSE.gratis, String(!!state.license.gratis));
                if (state.license.expira) localStorage.setItem(STORAGE_LICENSE.expira, state.license.expira);
            } else {
                Object.values(STORAGE_LICENSE).forEach((k) => localStorage.removeItem(k));
            }
        } catch { /* */ }
        applyStatus(state.license);
    }

    // -------------------------------------------------------------------------
    // Stats
    // -------------------------------------------------------------------------
    async function loadStats() {
        try {
            const r = await fetchWithLicense('/api/stats', { cache: 'no-store' });
            if (!r.ok) throw new Error('HTTP ' + r.status);
            const data = await r.json();
            const pessoas = data.pessoas ?? data.total_json ?? 0;
            const pastebin = data.pastebin ?? data.total_pastebin ?? 0;
            const setText = (id, v) => { const n = $(id); if (n) n.textContent = Number(v).toLocaleString('pt-BR'); };
            setText('#statPessoas', pessoas);
            setText('#statPastebin', pastebin);
            return data;
        } catch { return null; }
    }
    function tickUptime() {
        const u = $('#statUptime');
        if (!u) return;
        const start = state.bootTime;
        const update = () => {
            const s = Math.floor((Date.now() - start) / 1000);
            const h = String(Math.floor(s / 3600)).padStart(2, '0');
            const m = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
            const sec = String(s % 60).padStart(2, '0');
            u.textContent = `${h}:${m}:${sec}`;
        };
        update();
        setInterval(update, 1000);
    }

    // -------------------------------------------------------------------------
    // Mode tabs (search)
    // -------------------------------------------------------------------------
    function applyModePresentation(mode) {
        const label = MODE_LABELS[mode] || 'Termo';
        const input = $('#termoInput');
        const labelNode = $('.search-label > span:first-child');
        const outputMode = $('.output-mode');
        const form = $('#queryForm');
        if (input) {
            input.placeholder = PLACEHOLDERS[mode] || 'digite o termo…';
            input.setAttribute('aria-label', `${label} para consulta`);
        }
        if (labelNode) labelNode.textContent = label;
        if (outputMode) outputMode.textContent = label;
        if (form) form.setAttribute('aria-label', `Executar consulta por ${label}`);
    }

    function activateMode(btn, { focusInput = true, announce = true } = {}) {
        if (!btn) return;
        $$('.mode').forEach((b) => {
            const active = b === btn;
            b.classList.toggle('active', active);
            b.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        state.modo = btn.dataset.mode;
        applyModePresentation(state.modo);
        if (focusInput) $('#termoInput')?.focus();
        if (announce) setLiveMessage(`Modo ${MODE_LABELS[state.modo] || state.modo} selecionado`, 'polite');
    }

    function bindModes() {
        const modes = $$('.mode');
        modes.forEach((btn, index) => {
            btn.addEventListener('click', () => activateMode(btn));
            btn.addEventListener('keydown', (e) => {
                if (!['ArrowUp', 'ArrowDown', 'Home', 'End'].includes(e.key)) return;
                e.preventDefault();
                let nextIndex = index;
                if (e.key === 'ArrowDown') nextIndex = (index + 1) % modes.length;
                if (e.key === 'ArrowUp') nextIndex = (index - 1 + modes.length) % modes.length;
                if (e.key === 'Home') nextIndex = 0;
                if (e.key === 'End') nextIndex = modes.length - 1;
                activateMode(modes[nextIndex], { focusInput: false });
                modes[nextIndex].focus();
            });
        });
        const active = modes.find((btn) => btn.classList.contains('active')) || modes[0];
        activateMode(active, { focusInput: false, announce: false });
    }

    // -------------------------------------------------------------------------
    // History
    // -------------------------------------------------------------------------
    function loadHistory() {
        try { state.history = JSON.parse(localStorage.getItem(STORAGE_HISTORY) || '[]'); } catch { state.history = []; }
        renderHistory();
    }
    function saveHistory() {
        try { localStorage.setItem(STORAGE_HISTORY, JSON.stringify(state.history.slice(0, HISTORY_LIMIT))); } catch { /* */ }
    }
    function pushHistory(termo, modo) {
        if (!termo) return;
        state.history = [{ termo, modo, t: Date.now() }, ...state.history.filter((h) => !(h.termo === termo && h.modo === modo))].slice(0, HISTORY_LIMIT);
        saveHistory();
        renderHistory();
    }
    function renderHistory() {
        const block = $('#historyBlock');
        const area = $('#historyArea');
        if (!block || !area) return;
        if (!state.history.length) { block.hidden = true; area.innerHTML = ''; return; }
        block.hidden = false;
        area.innerHTML = '';
        state.history.forEach((h) => {
            const label = MODE_LABELS[h.modo] || h.modo || 'consulta';
            const timestamp = new Date(h.t).toLocaleString('pt-BR');
            const tag = el('button', {
                class: 'h-tag',
                type: 'button',
                title: timestamp,
                'aria-label': `Repetir consulta por ${label}: ${h.termo}`,
                onclick: () => {
                    const input = $('#termoInput');
                    if (input) input.value = h.termo;
                    const m = $$('.mode').find((modeButton) => modeButton.dataset.mode === h.modo);
                    if (m) activateMode(m, { focusInput: true, announce: false });
                    setLiveMessage(`Consulta por ${label} carregada`, 'polite');
                },
            },
                el('span', { class: 'h-mode' }, label),
                el('span', { class: 'h-term' }, h.termo),
                el('span', { class: 'h-arrow', 'aria-hidden': 'true' }, '↗'),
            );
            area.appendChild(tag);
        });
    }

    // -------------------------------------------------------------------------
    // Search
    // -------------------------------------------------------------------------
    function setLoading(on) {
        const btn = $('#buscarBtn');
        setButtonBusy(btn, on, 'Executando…');
        const input = $('#termoInput');
        if (input) {
            input.style.opacity = on ? 0.55 : 1;
            input.setAttribute('aria-busy', on ? 'true' : 'false');
        }
        const output = $('#outputBody');
        if (output) output.setAttribute('aria-busy', on ? 'true' : 'false');
        if (on) setOutputState('consultando…');
    }

    async function executarBusca() {
        const input = $('#termoInput');
        const termo = (input?.value || '').trim();
        if (!termo) {
            toast('Digite um termo para buscar.', 'warn', 'Atenção');
            input?.focus();
            return;
        }
        if (termo.length < 2) {
            toast('O termo precisa ter pelo menos 2 caracteres.', 'warn', 'Atenção');
            input?.focus();
            return;
        }

        const seq = ++state.requestSeq;
        const body = $('#outputBody');
        if (!body) return;
        const label = MODE_LABELS[state.modo] || state.modo;
        body.innerHTML = '';
        body.appendChild(el('div', { class: 'loading-row', role: 'status' },
            el('span', { class: 'bar', 'aria-hidden': 'true' }, el('i'), el('i'), el('i'), el('i'), el('i')),
            el('span', null, `Consultando ${label} “${termo}”…`),
        ));
        setLoading(true);
        setLiveMessage(`Consultando ${label}: ${termo}`, 'polite');

        try {
            const r = await fetchWithLicense('/buscar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: `modo=${encodeURIComponent(state.modo)}&termo=${encodeURIComponent(termo)}`,
            });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            const data = await r.json();
            if (seq !== state.requestSeq) return;
            body.innerHTML = '';
            if (data.erro) {
                setOutputState('erro na consulta');
                renderStatusBlock('error', 'Não foi possível concluir', data.erro);
                toast(data.erro, 'err', 'Erro');
                return;
            }
            if (!data.encontrado) {
                const message = data.mensagem || 'Nenhum resultado encontrado.';
                setOutputState('sem correspondência');
                renderStatusBlock('warn', 'Nenhum resultado', message);
                setLiveMessage(`Nenhum resultado para ${label}: ${termo}`, 'polite');
                return;
            }
            setOutputState('consulta concluída');
            renderResultado(data);
            pushHistory(termo, state.modo);
            setLiveMessage(`${data.total ?? (data.dados ? 1 : 0)} resultado(s) carregado(s)`, 'polite');
        } catch (err) {
            if (seq !== state.requestSeq) return;
            body.innerHTML = '';
            const message = `Falha de conexão: ${err.message}`;
            setOutputState('erro na consulta');
            renderStatusBlock('error', 'Não foi possível concluir', message);
            toast(message, 'err', 'Erro');
        } finally {
            if (seq === state.requestSeq) setLoading(false);
        }
    }

    function renderStatusBlock(kind, title, msg) {
        const body = $('#outputBody');
        if (!body) return;
        const ics = { error: '!', success: '✓', warn: '!' };
        body.appendChild(el('div', {
            class: `status-block ${kind}`,
            role: kind === 'error' ? 'alert' : 'status',
        },
            el('span', { class: 'ic', 'aria-hidden': 'true' }, ics[kind] || '·'),
            el('div', { class: 'body' },
                el('div', { class: 'title' }, title),
                el('div', { class: 'msg' }, msg),
            ),
        ));
    }

    function renderResultado(data) {
        const body = $('#outputBody');
        if (!body) return;
        const wrap = el('div');
        const label = MODE_LABELS[data.modo] || data.modo || 'consulta';
        wrap.appendChild(el('div', { class: 'section-title' },
            `Consulta por ${label}`,
            el('span', { class: 'badge' }, data.modo === 'cpf' ? 'detalhe completo' : `${data.total ?? 0} resultado${(data.total ?? 0) !== 1 ? 's' : ''}`),
        ));
        if (data.modo === 'cpf' && data.dados) {
            wrap.appendChild(renderDetailCard(data.dados, data.fonte || 'SQLite'));
        } else if (Array.isArray(data.resultados) && data.resultados.length) {
            wrap.appendChild(el('div', { class: 'result-meta' },
                el('strong', null, String(data.total ?? data.resultados.length)),
                ` resultado${data.total === 1 ? '' : 's'} · selecione uma linha para abrir o detalhe completo`,
            ));
            const resultsList = el('div', { role: 'list', 'aria-label': `Resultados por ${label}` });
            data.resultados.forEach((r) => resultsList.appendChild(renderResultCard(r)));
            wrap.appendChild(resultsList);
        } else {
            wrap.appendChild(renderStatusBlock('warn', 'Nenhum resultado', 'Nenhum resultado retornado.'));
        }
        body.appendChild(wrap);
        body.scrollTop = 0;
    }

    function renderDetailCard(d, fonte) {
        const card = el('div', { class: 'detail-card' });
        card.appendChild(el('div', { class: 'detail-head' },
            el('div', { class: 'detail-name' }, d.nome || '(sem nome)'),
            el('div', { class: 'detail-cpf' }, formatCpf(d.cpf)),
            el('div', { class: 'detail-source' }, (fonte || 'sqlite').toUpperCase()),
        ));
        const fields = [
            ['mãe', d.nome_mae], ['sexo', d.sexo],
            ['nascimento', d.data_nasc ? `${d.data_nasc}${d.idade ? ` (${d.idade} anos)` : ''}` : ''],
            ['renda', d.renda], ['escolaridade', d.escolaridade],
            ['classe', d.classe_social], ['profissão', d.profissao],
        ];
        fields.forEach(([k, v]) => { if (v) card.appendChild(makeKV(k, v)); });
        appendSection(card, 'telefones', d.telefones, (t) => {
            const li = el('li', null, escapeHtml(t.numero || ''));
            if (t.whatsapp) li.appendChild(el('span', { class: 'wa' }, '● whatsapp'));
            if (t.tipo) li.appendChild(el('span', { class: 'pill' }, tipoTel(t.tipo)));
            return li;
        });
        appendSection(card, 'emails', d.emails, (e) => el('li', null, escapeHtml(e)));
        appendSection(card, 'endereços', d.enderecos, (e) => el('li', null,
            `${escapeHtml(e.logradouro || '')}${e.numero ? `, ${escapeHtml(e.numero)}` : ''}${e.bairro ? ` — ${escapeHtml(e.bairro)}` : ''}${e.cidade ? ` · ${escapeHtml(e.cidade)}/${escapeHtml(e.uf || '')}` : ''}${e.cep ? ` · cep ${escapeHtml(e.cep)}` : ''}`));
        appendSection(card, 'veículos', d.veiculos, (v) => el('li', null, `${escapeHtml(v.placa || '')} :: ${escapeHtml(v.modelo || '')}${v.ano ? ` (${v.ano})` : ''}`));
        appendSection(card, 'parentes', d.parentes, (p) => {
            const li = el('li', null, `${escapeHtml(p.nome || '')}${p.grau ? ` (${escapeHtml(p.grau)}${p.idade ? `, ${p.idade}a` : ''})` : ''}`);
            if (p.cpf) li.appendChild(el('span', { class: 'meta' }, `cpf ${formatCpf(p.cpf)}`));
            return li;
        });
        appendSection(card, 'empresas', d.empresas, (emp) => {
            const li = el('li', null, escapeHtml(emp.razao || ''));
            if (emp.cnpj) li.appendChild(el('span', { class: 'meta' }, `cnpj ${emp.cnpj}`));
            return li;
        });
        const vaz = d.vazamentos || 0;
        card.appendChild(makeKV('vazamentos', vaz > 0 ? `${vaz} credenciais expostas` : '0', vaz > 0 ? 'tag' : 'dim'));
        if (Array.isArray(d.fotos) && d.fotos.length) {
            card.appendChild(makeKV('fotos', `${d.fotos.length} disponível${d.fotos.length > 1 ? 'is' : ''}`, 'tag'));
        }
        return card;
    }
    function tipoTel(t) { const m = { 1: 'residencial', 2: 'celular', 3: 'comercial' }; return m[t] || `tipo ${t}`; }
    function makeKV(k, v, vClass) {
        return el('div', { class: 'kv' },
            el('span', { class: 'k' }, k),
            el('span', { class: 'v' + (vClass ? ' ' + vClass : '') }, v),
        );
    }
    function appendSection(parent, title, arr, buildLi) {
        if (!Array.isArray(arr) || !arr.length) return;
        parent.appendChild(el('div', { class: 'section-title' }, title, el('span', { class: 'badge' }, `${arr.length} item${arr.length !== 1 ? 'ns' : ''}`)));
        const ul = el('ul', { class: 'list' });
        arr.forEach((it) => ul.appendChild(buildLi(it)));
        parent.appendChild(ul);
    }
    function renderResultCard(r) {
        const name = r.nome || '(sem nome)';
        const cpf = formatCpf(r.cpf);
        const button = el('button', {
            class: 'result-card',
            type: 'button',
            'aria-label': `Abrir o registro de ${name}, CPF ${cpf}`,
            onclick: () => {
                if (!r.cpf) return;
                const input = $('#termoInput');
                if (input) input.value = String(r.cpf).replace(/\D/g, '');
                const m = $('.mode[data-mode="cpf"]');
                if (m) activateMode(m, { focusInput: false, announce: false });
                executarBusca();
            },
        },
            el('span', { class: 'rc-name' }, name),
            el('span', { class: 'rc-cpf' }, cpf),
            el('span', { class: 'rc-arrow', 'aria-hidden': 'true' }, '→'),
        );
        return el('div', { role: 'listitem' }, button);
    }
    function limpar() {
        const input = $('#termoInput');
        if (input) { input.value = ''; input.focus(); }
        const body = $('#outputBody');
        if (!body) return;
        body.innerHTML = '';
        body.appendChild(el('div', { class: 'empty' },
            el('span', { class: 'empty-icon', 'aria-hidden': 'true' }, '⌕'),
            el('p', { class: 'empty-title' }, 'Pronto para consultar'),
            el('p', { class: 'muted' }, 'Selecione um modo e execute uma busca para ver os registros.'),
        ));
        setLoading(false);
        setOutputState('pronto para consulta');
        setLiveMessage('Consulta limpa. Pronto para uma nova busca.', 'polite');
    }

    // -------------------------------------------------------------------------
    // License modal
    // -------------------------------------------------------------------------
    function openLicenca(trigger) {
        const modal = $('#licencaModal');
        if (!modal) return;
        state.modalTrigger = trigger && typeof trigger.focus === 'function' ? trigger : document.activeElement;
        state.modalBodyOverflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        modal.classList.add('open');
        modal.removeAttribute('hidden');
        modal.setAttribute('aria-hidden', 'false');
        setLiveMessage('Painel de licença aberto.', 'polite');
        window.setTimeout(() => $('#chaveInput')?.focus(), 60);
    }

    function closeLicenca() {
        const modal = $('#licencaModal');
        if (!modal) return;
        modal.classList.remove('open');
        modal.setAttribute('hidden', '');
        modal.setAttribute('aria-hidden', 'true');
        document.body.style.overflow = state.modalBodyOverflow;
        const trigger = state.modalTrigger;
        state.modalTrigger = null;
        if (trigger && document.contains(trigger) && typeof trigger.focus === 'function') trigger.focus();
        else $('#openLicenca')?.focus();
        setLiveMessage('Painel de licença fechado.', 'polite');
    }

    function trapModalFocus(event) {
        const modal = $('#licencaModal');
        if (!modal || event.key !== 'Tab') return;
        const elements = focusableIn(modal);
        if (!elements.length) return;
        const first = elements[0];
        const last = elements[elements.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    }

    function setMsg(text, kind = 'info') {
        const message = $('#licencaMensagem');
        if (!message) return;
        message.textContent = text;
        message.classList.remove('ok', 'err', 'info');
        message.classList.add(kind);
        message.setAttribute('role', kind === 'err' ? 'alert' : 'status');
        message.setAttribute('aria-live', kind === 'err' ? 'assertive' : 'polite');
    }
    async function validarLicenca() {
        const input = $('#chaveInput');
        const button = $('#validarBtn');
        const chave = (input?.value || '').trim().toUpperCase();
        if (!chave) {
            input?.setAttribute('aria-invalid', 'true');
            setMsg('Informe uma chave de licença.', 'err');
            input?.focus();
            return;
        }
        if (!/^[A-Z0-9]{4}(-[A-Z0-9]{4}){3}$/.test(chave)) {
            input?.setAttribute('aria-invalid', 'true');
            setMsg('Formato inválido. Use XXXX-XXXX-XXXX-XXXX.', 'err');
            input?.focus();
            return;
        }
        input?.setAttribute('aria-invalid', 'false');
        setButtonBusy(button, true, 'Validando…');
        setMsg('Validando chave…', 'info');
        try {
            const r = await fetch('/api/validar', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ chave }) });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            const data = await r.json();
            if (data.valida) {
                unlockAccess({ ativa: true, chave, usuario: data.usuario || 'usuário', gratis: !!data.gratis, expira: data.expira || '' });
                setMsg(`Licença ${data.gratis ? 'gratuita' : 'premium'} ativada para ${data.usuario || 'usuário'}.`, 'ok');
                toast('Licença ativada com sucesso.', 'ok', 'Sucesso');
                setLiveMessage('Licença ativada com sucesso.', 'polite');
                window.setTimeout(closeLicenca, 900);
            } else {
                const message = data.motivo || 'Chave inválida.';
                setMsg(message, 'err');
                toast(message, 'err', 'Erro');
            }
        } catch (err) {
            setMsg(`Não foi possível validar a licença: ${err.message}`, 'err');
            toast('Não foi possível validar a licença.', 'err', 'Erro');
        } finally {
            setButtonBusy(button, false);
        }
    }

    async function loginWithLicense() {
        const input = $('#loginLicenseKey');
        const button = $('#loginSubmit');
        const chave = (input?.value || '').trim().toUpperCase();
        if (!chave) {
            input?.setAttribute('aria-invalid', 'true');
            setLoginMessage('Informe uma chave de licença.', 'err');
            input?.focus();
            return;
        }
        if (!/^[A-Z0-9]{4}(-[A-Z0-9]{4}){3}$/.test(chave)) {
            input?.setAttribute('aria-invalid', 'true');
            setLoginMessage('Formato inválido. Use XXXX-XXXX-XXXX-XXXX.', 'err');
            input?.focus();
            return;
        }
        input?.setAttribute('aria-invalid', 'false');
        setButtonBusy(button, true, 'Validando…');
        setLoginMessage('Validando sua licença…', 'info');
        try {
            const r = await fetch('/api/validar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chave }),
            });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            const data = await r.json();
            if (!data.valida) {
                const message = data.motivo || 'Chave inválida ou expirada.';
                setLoginMessage(message, 'err');
                toast(message, 'err', 'Acesso negado');
                return;
            }
            unlockAccess({ ativa: true, chave, usuario: data.usuario || 'usuário', gratis: !!data.gratis, expira: data.expira || '' });
            toast(`Bem-vindo, ${data.usuario || 'usuário'}.`, 'ok', 'Login realizado');
        } catch (err) {
            setLoginMessage(`Não foi possível validar a licença: ${err.message}`, 'err');
            toast('Não foi possível entrar no painel.', 'err', 'Erro');
        } finally {
            setButtonBusy(button, false);
        }
    }

    async function gerarGratisNoLogin() {
        const button = $('#loginFreeBtn');
        setButtonBusy(button, true, 'Gerando…');
        setLoginMessage('Gerando sua licença gratuita…', 'info');
        try {
            const r = await fetch('/api/gerar_gratis', { method: 'POST' });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            const data = await r.json();
            if (data.erro) {
                setLoginMessage(data.erro, 'err');
                return;
            }
            const input = $('#loginLicenseKey');
            if (input && data.chave) {
                input.value = data.chave;
                input.setAttribute('aria-invalid', 'false');
                setLoginMessage(`Chave criada por ${data.validade} dias. Clique em entrar para continuar.`, 'ok');
                input.focus();
            }
        } catch (err) {
            setLoginMessage(`Não foi possível gerar a licença: ${err.message}`, 'err');
            toast('Não foi possível gerar a licença gratuita.', 'err', 'Erro');
        } finally {
            setButtonBusy(button, false);
        }
    }

    async function gerarGratis() {
        const button = $('#gratisBtn');
        setButtonBusy(button, true, 'Gerando…');
        setMsg('Gerando licença gratuita…', 'info');
        try {
            const r = await fetch('/api/gerar_gratis', { method: 'POST' });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            const data = await r.json();
            if (data.erro) { setMsg(data.erro, 'err'); return; }
            const input = $('#chaveInput');
            if (input && data.chave) {
                input.value = data.chave;
                input.setAttribute('aria-invalid', 'false');
                input.focus();
            }
            setMsg(`Chave gerada por ${data.validade} dias. Clique em ativar para concluir.`, 'ok');
            toast('Chave gratuita gerada.', 'ok', 'Sucesso');
        } catch (err) {
            setMsg(`Não foi possível gerar a licença: ${err.message}`, 'err');
            toast('Não foi possível gerar a licença.', 'err', 'Erro');
        } finally {
            setButtonBusy(button, false);
        }
    }

    // A emissão paga é administrativa e não fica disponível no navegador.
    // Use `python -m app.gerar_paga` no servidor para emitir uma chave.
    async function gerarPaga() {
        const button = $('#pagaBtn');
        const dias = parseInt($('#pagaDias')?.value || '30', 10);
        const usuario = ($('#pagaUsuario')?.value || '').trim() || 'cliente';
        setButtonBusy(button, true, 'Gerando…');
        setMsg(`Gerando licença paga de ${dias} dias para ${usuario}…`, 'info');
        try {
            const r = await fetch('/api/gerar_paga', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dias, usuario }) });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            const data = await r.json();
            if (data.erro) { setMsg(data.erro, 'err'); return; }
            const input = $('#chaveInput');
            if (input && data.chave) {
                input.value = data.chave;
                input.setAttribute('aria-invalid', 'false');
                input.focus();
            }
            setMsg(`Licença paga gerada para ${data.usuario || usuario}. Valide a chave para ativar.`, 'ok');
            toast(`Licença paga de ${dias} dias gerada.`, 'ok', 'Sucesso');
        } catch (err) {
            setMsg(`Não foi possível gerar a licença: ${err.message}`, 'err');
            toast('Não foi possível gerar a licença.', 'err', 'Erro');
        } finally {
            setButtonBusy(button, false);
        }
    }
    async function restoreLicense() {
        try {
            const chave = localStorage.getItem(STORAGE_LICENSE.chave);
            if (!chave) {
                setAccess(false);
                setLiveMessage('Nenhuma licença ativa. Informe uma chave para entrar.', 'polite');
                return false;
            }
            const cachedUser = localStorage.getItem(STORAGE_LICENSE.usuario) || 'usuário';
            const cachedExp = localStorage.getItem(STORAGE_LICENSE.expira) || '';
            const r = await fetch('/api/validar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chave }),
            });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            const data = await r.json();
            if (!data.valida) {
                lockAccess('A licença salva é inválida ou expirou.');
                return false;
            }
            unlockAccess({ ativa: true, chave, usuario: data.usuario || cachedUser, gratis: !!data.gratis, expira: data.expira || cachedExp });
            toast(`Sessão restaurada para ${data.usuario || cachedUser}.`, 'info', 'Sessão');
            return true;
        } catch (err) {
            setAccess(false);
            setLoginMessage(`Não foi possível validar a licença salva: ${err.message}`, 'err');
            setLiveMessage(`Não foi possível validar a licença salva: ${err.message}`, 'assertive');
            return false;
        }
    }

    // -------------------------------------------------------------------------
    // Upload
    // -------------------------------------------------------------------------
    function bindUpload() {
        const dz = $('#dropzone');
        const input = $('#fileInput');
        if (!dz || !input) return;

        const openPicker = () => input.click();
        dz.addEventListener('click', openPicker);
        dz.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                openPicker();
            }
        });
        dz.setAttribute('tabindex', '0');
        dz.setAttribute('role', 'button');
        dz.setAttribute('aria-label', 'Selecionar arquivos para upload');
        dz.setAttribute('aria-keyshortcuts', 'Enter Space');

        input.addEventListener('change', (e) => {
            const files = Array.from(e.target.files || []);
            if (files.length) uploadFiles(files);
            input.value = '';
            window.setTimeout(() => dz.focus(), 0);
        });

        ['dragenter', 'dragover'].forEach((ev) => dz.addEventListener(ev, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dz.classList.add('dragover');
            dz.setAttribute('aria-label', 'Solte os arquivos para iniciar o upload');
        }));
        ['dragleave', 'drop'].forEach((ev) => dz.addEventListener(ev, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dz.classList.remove('dragover');
            dz.setAttribute('aria-label', 'Selecionar arquivos para upload');
        }));
        dz.addEventListener('drop', (e) => {
            const files = Array.from(e.dataTransfer?.files || []);
            if (files.length) uploadFiles(files);
        });

        $('#refreshFiles')?.addEventListener('click', loadFileList);
    }

    function uploadFiles(files) {
        const list = $('#uploadList');
        if (!list || !files.length) return;
        const items = files.map((f) => makeUploadItem(f));
        items.forEach((i) => list.appendChild(i.el));

        const fd = new FormData();
        files.forEach((f) => fd.append('files', f, f.name));

        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/upload');
        if (state.license?.chave) xhr.setRequestHeader('X-License-Key', state.license.chave);

        const progress = $('#uploadProgress');
        const fill = $('#upFill');
        const pct = $('#upPct');
        const lbl = $('#upLabel');
        if (!progress || !fill || !pct || !lbl) return;
        progress.hidden = false;
        progress.setAttribute('role', 'status');
        progress.setAttribute('aria-busy', 'true');
        const bar = progress.querySelector('.up-bar');
        if (bar) {
            bar.setAttribute('role', 'progressbar');
            bar.setAttribute('aria-valuemin', '0');
            bar.setAttribute('aria-valuemax', '100');
            bar.setAttribute('aria-valuenow', '0');
            bar.setAttribute('aria-label', 'Progresso do upload');
        }
        fill.style.width = '0%';
        pct.textContent = '0%';
        lbl.textContent = `Enviando ${files.length} arquivo${files.length !== 1 ? 's' : ''}…`;
        setLiveMessage(`Upload iniciado para ${files.length} arquivo${files.length !== 1 ? 's' : ''}.`, 'polite');

        xhr.upload.onprogress = (e) => {
            if (!e.lengthComputable) return;
            const p = Math.round((e.loaded / e.total) * 100);
            fill.style.width = p + '%';
            pct.textContent = p + '%';
            if (bar) bar.setAttribute('aria-valuenow', String(p));
        };
        xhr.onload = () => {
            let data = {};
            try { data = JSON.parse(xhr.responseText || '{}'); } catch { data = {}; }
            const ok = xhr.status >= 200 && xhr.status < 300 && data.ok;
            progress.setAttribute('aria-busy', 'false');
            if (ok) {
                lbl.textContent = 'Processado';
                pct.textContent = '100%';
                fill.style.width = '100%';
                if (bar) bar.setAttribute('aria-valuenow', '100');
                (data.salvos || []).forEach((s) => {
                    const it = items.find((i) => i.file.name === s.original || i.file.name === s.nome);
                    if (it) it.markOk(s);
                });
                (data.erros || []).forEach((er) => {
                    const it = items.find((i) => i.file.name === er.nome);
                    if (it) it.markErr(er.erro);
                });
                const reimported = data.reimport && data.reimport.stats;
                const summary = reimported
                    ? ` · banco: ${reimported.pessoas} pessoas, ${reimported.pastebin} CPFs`
                    : '';
                const saved = (data.salvos || []).length;
                toast(`Upload concluído · ${saved} salvo${saved !== 1 ? 's' : ''}${summary}`, 'ok', 'Sucesso');
                setLiveMessage(`Upload concluído. ${saved} arquivo${saved !== 1 ? 's' : ''} salvo${saved !== 1 ? 's' : ''}.`, 'polite');
                if (data.reimport_erro) toast('Reimportação: ' + data.reimport_erro, 'warn', 'Atenção');
                loadFileList();
                loadStats();
                window.setTimeout(() => { progress.hidden = true; }, 1800);
            } else {
                lbl.textContent = 'Falhou';
                const msg = (data && (data.erro || data.reimport_erro)) || `HTTP ${xhr.status}`;
                items.forEach((i) => i.markErr(msg));
                toast(msg, 'err', 'Erro');
                setLiveMessage(`Upload não concluído: ${msg}`, 'assertive');
            }
        };
        xhr.onerror = () => {
            progress.setAttribute('aria-busy', 'false');
            lbl.textContent = 'Falhou';
            items.forEach((i) => i.markErr('Falha de rede.'));
            toast('Falha de rede no upload.', 'err', 'Erro');
            setLiveMessage('Upload não concluído por falha de rede.', 'assertive');
        };
        xhr.send(fd);
    }

    function makeUploadItem(file) {
        const status = el('div', { class: 'ui-status' }, 'Aguardando…');
        const ico = el('div', { class: 'ui-ic', 'aria-hidden': 'true' }, '↑');
        const wrap = el('div', {
            class: 'upload-item',
            role: 'listitem',
            'aria-label': `${file.name}, ${formatBytes(file.size)}, aguardando`,
        }, ico,
            el('div', { class: 'ui-name' }, file.name, el('div', { class: 'ui-meta' }, formatBytes(file.size))),
            status,
        );
        return {
            file,
            el: wrap,
            markOk(s) {
                wrap.classList.add('ok');
                ico.textContent = '✓';
                status.textContent = `Salvo · ${s.tamanho_h || ''}`;
                wrap.setAttribute('aria-label', `${file.name}, upload concluído`);
            },
            markErr(msg) {
                wrap.classList.add('err');
                ico.textContent = '×';
                status.textContent = msg || 'Falha no upload.';
                wrap.setAttribute('aria-label', `${file.name}, falha no upload: ${msg || 'erro desconhecido'}`);
            },
        };
    }

    function formatBytes(n) {
        if (n < 1024) return `${n} B`;
        if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
        if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
        return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
    }

    async function loadFileList() {
        const body = $('#filesBody');
        if (!body) return;
        body.setAttribute('aria-busy', 'true');
        body.innerHTML = '<div class="muted files-empty">Carregando arquivos…</div>';
        try {
            const r = await fetchWithLicense('/api/list', { cache: 'no-store' });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            const data = await r.json();
            renderFileList(data.arquivos || []);
            const c = $('#filesCount');
            if (c) c.textContent = `${(data.arquivos || []).length} arquivo${(data.arquivos || []).length !== 1 ? 's' : ''}`;
        } catch (err) {
            body.innerHTML = '';
            body.appendChild(el('div', { class: 'status-block error', role: 'alert' },
                el('span', { class: 'ic', 'aria-hidden': 'true' }, '!'),
                el('div', { class: 'body' },
                    el('div', { class: 'title' }, 'Não foi possível carregar os arquivos'),
                    el('div', { class: 'msg' }, err.message),
                ),
            ));
            setLiveMessage(`Não foi possível carregar os arquivos: ${err.message}`, 'assertive');
        } finally {
            body.setAttribute('aria-busy', 'false');
        }
    }

    function renderFileList(files) {
        const body = $('#filesBody');
        if (!body) return;
        if (!files.length) {
            body.innerHTML = '<div class="muted files-empty">Nenhum arquivo em databases/.</div>';
            return;
        }
        body.innerHTML = '';
        body.setAttribute('role', 'list');
        body.setAttribute('aria-label', 'Arquivos em databases');
        files.forEach((f) => {
            const name = f.nome || 'arquivo sem nome';
            const item = el('div', {
                class: 'file-item' + (f.suportado ? '' : ' unsupported'),
                role: 'listitem',
                'aria-label': `${name}, ${f.tamanho_h || 'tamanho desconhecido'}`,
            },
                el('span', { class: 'fi-ic', 'aria-hidden': 'true' }, '·'),
                el('span', { class: 'fi-name' }, name),
                el('span', { class: 'fi-size' }, f.tamanho_h || '—'),
                el('button', {
                    class: 'fi-del',
                    type: 'button',
                    title: `Excluir ${name}`,
                    'aria-label': 'Excluir ' + name,
                    onclick: () => deleteFile(name, item),
                }, '×'),
            );
            body.appendChild(item);
        });
    }

    async function deleteFile(nome, item) {
        if (!confirm(`Excluir "${nome}"?`)) return;
        try {
            const r = await fetchWithLicense('/api/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ nome }),
            });
            const data = await r.json();
            if (data.ok) {
                item.remove();
                toast(`"${nome}" removido.`, 'ok', 'Sucesso');
                setLiveMessage(`Arquivo ${nome} removido.`, 'polite');
                loadFileList();
                loadStats();
            } else {
                const message = data.erro || 'Falha ao excluir o arquivo.';
                toast(message, 'err', 'Erro');
                setLiveMessage(message, 'assertive');
            }
        } catch (err) {
            toast(err.message, 'err', 'Erro');
            setLiveMessage(`Falha ao excluir o arquivo: ${err.message}`, 'assertive');
        }
    }

    // -------------------------------------------------------------------------
    // Misc
    // -------------------------------------------------------------------------
    function bindKeyMask() {
        const input = $('#chaveInput');
        if (!input) return;
        input.addEventListener('input', (e) => {
            let v = e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '');
            const parts = [];
            for (let i = 0; i < v.length && i < 16; i += 4) parts.push(v.slice(i, i + 4));
            e.target.value = parts.join('-');
        });
    }
    function bindShortcuts() {
        document.addEventListener('keydown', (e) => {
            const modalOpen = $('#licencaModal')?.classList.contains('open');
            if (modalOpen) {
                if (e.key === 'Escape') {
                    e.preventDefault();
                    closeLicenca();
                    return;
                }
                trapModalFocus(e);
                return;
            }
            if (e.key === '/' && document.activeElement !== $('#termoInput') && document.activeElement !== $('#chaveInput')) {
                e.preventDefault();
                $('#termoInput')?.focus();
                return;
            }
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
                e.preventDefault();
                openLicenca($('#openLicenca'));
                return;
            }
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'l') {
                e.preventDefault();
                limpar();
                return;
            }
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'u') {
                e.preventDefault();
                switchTab('upload', { focusTab: true });
            }
        });
    }

    function bindEvents() {
        const loginForm = $('#licenseLoginForm');
        if (loginForm) loginForm.addEventListener('submit', (e) => { e.preventDefault(); loginWithLicense(); });
        $('#loginFreeBtn')?.addEventListener('click', gerarGratisNoLogin);
        $('#loginLicenseKey')?.addEventListener('input', (e) => {
            let value = e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '');
            const parts = [];
            for (let i = 0; i < value.length && i < 16; i += 4) parts.push(value.slice(i, i + 4));
            e.target.value = parts.join('-');
        });

        const form = $('#queryForm');
        if (form) form.addEventListener('submit', (e) => { e.preventDefault(); executarBusca(); });
        const input = $('#termoInput');
        if (input) input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                executarBusca();
            }
        });
        $('#limparBtn')?.addEventListener('click', limpar);
        $('#openLicenca')?.addEventListener('click', (e) => openLicenca(e.currentTarget));
        $('#licChip')?.addEventListener('click', (e) => openLicenca(e.currentTarget));
        $('#logoutBtn')?.addEventListener('click', logout);
        $('#clearHistoryBtn')?.addEventListener('click', () => {
            state.history = [];
            saveHistory();
            renderHistory();
            toast('Histórico limpo.', 'info', 'Histórico');
        });

        $('#closeModalBtn')?.addEventListener('click', closeLicenca);
        const modal = $('#licencaModal');
        if (modal) modal.addEventListener('click', (e) => { if (e.target === modal) closeLicenca(); });
        $('#validarBtn')?.addEventListener('click', validarLicenca);
        $('#gratisBtn')?.addEventListener('click', gerarGratis);
        $('#pagaBtn')?.addEventListener('click', gerarPaga);
        $('#chaveInput')?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                validarLicenca();
            }
        });
        bindKeyMask();
    }

    async function boot() {
        ensureLiveRegion();
        bindTabs();
        bindModes();
        bindEvents();
        bindShortcuts();
        bindUpload();
        loadHistory();
        const authenticated = await restoreLicense();
        if (authenticated) {
            await loadStats();
            tickUptime();
            setInterval(loadStats, 30000);
            setTimeout(() => $('#termoInput')?.focus(), 200);
        } else {
            setTimeout(() => $('#loginLicenseKey')?.focus(), 200);
        }
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
    else boot();
})();
