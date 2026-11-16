
/* PAINEL DA REVISÃO LIGHT (regimento §1-B, 16/11/2026). O mesmo modelo do plenário
  (painel-conselho.html: folha de estilo, corpo, ata e rodapé), com este script no lugar do
  painel-conselho.js: o painel_fragmento.py o escolhe quando a sessão é `variante: light`. Um
  revisor percorre em série os quatro mandatos e fecha com a síntese; quórum de veto. Sem
  plenário, sem placar de maioria: não é deliberação colegiada, e o painel o diz. */
const MAND = [
 { id:'merito',       nome:'Mérito',       cor:'#3b5fa3' },
 { id:'coerencia',    nome:'Coerência',    cor:'#2a8a7c' },
 { id:'escrita',      nome:'Escrita',      cor:'#7a4fa3' },
 { id:'conformidade', nome:'Conformidade', cor:'#a3793b' }
];
const PASSOS = [['abertura','Abertura'],['merito','Mérito'],['coerencia','Coerência'],['escrita','Escrita'],
 ['conformidade','Conformidade'],['sintese','Síntese'],['fim','Decisão']];
const FAIXA = 'REVISÃO LIGHT — revisão por um único revisor em série, não é deliberação colegiada';
/* Mesma busca do plenário no Cowork (painel-conselho.js): o arquivo mais novo de /sessions/<sessão>/mnt. */
const POLL = 'l=$(find /sessions/*/mnt -maxdepth 3 \\( -name CONSELHO_STATUS.json -o -name "CONSELHO_STATUS_*.json" \\) 2>/dev/null); f=; ' +
 'if [ -n "$l" ]; then set -f; IFS=\'\n\'; f=$(ls -t $l 2>/dev/null | head -1); fi; ' +
 'if [ -n "$f" ]; then cat "$f"; else echo NOFILE; fi';
const BOOT = /*ESTADO_INLINE*/ null; // modo inline: substituir 'null' pelo JSON do estado
const STATE_PATH = /*STATE_PATH*/ null; // caminho EXATO do estado: o painel_fragmento.py o injeta junto com o BOOT
function shq(s) { return "'" + String(s).replace(/'/g, "'\\''") + "'"; }
const POLL_EXATO = STATE_PATH ? 'f=' + shq(STATE_PATH) + '; if [ -f "$f" ]; then cat "$f"; else echo NOFILE; fi' : null;
let estado = BOOT, online = false;

/* ESCAPE, como no plenário: todo valor do estado que entra em innerHTML passa por esc() (o texto do
  revisor é DADO, nunca marcação). As demais funções devolvem só vocabulário fixo. */
function txt(v) { const t = typeof v; return (t === 'string' || t === 'number' || t === 'boolean') ? String(v) : ''; }
function esc(v) {
 return txt(v).replace(/[&<>"']/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}
function classeQuem(q) {
 let s = txt(q);
 if (s.normalize) s = s.normalize('NFD').replace(/[̀-ͯ]/g, '');
 return s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}
function semNome(q, t) {
 const qm = txt(q), tx = txt(t), r = tx.slice(qm.length);
 return (qm && tx.indexOf(qm) === 0 && /^[:\s]+\S/.test(r)) ? r.replace(/^[:\s]+/, '') : tx;
}
function p2(n) { return (n < 10 ? '0' : '') + n; }
function quando(iso) {
 const d = txt(iso) ? new Date(txt(iso)) : null;
 if (!d || isNaN(d.getTime())) return '';
 return p2(d.getDate()) + '/' + p2(d.getMonth() + 1) + ' ' + p2(d.getHours()) + ':' + p2(d.getMinutes());
}
function hora(iso) { const q = quando(iso); return q ? q.slice(6) : ''; }
function obj(v) { return v && typeof v === 'object' && !Array.isArray(v) ? v : null; }
function lista(v) { return Array.isArray(v) ? v.filter(obj) : []; }
function instante(e) {
 if (quando(e.atualizado)) return e.atualizado;
 const evs = lista(e.eventos).filter(ev => quando(ev.em));
 return evs.length ? evs[evs.length - 1].em : '';
}
const VOTOS = ['aprovar', 'devolver'];
function votou(v) { return !!v && VOTOS.indexOf(v.voto) >= 0 && !!txt(v.agente_id).trim() && !!txt(v.fundamentacao).trim(); }
function fimDe(e) { return e.fase === 'aprovado' || e.fase === 'devolvido'; }
/* O catálogo vem do conversor (conselho_sessao_base.CATALOGO_LIGHT); o poll lê o arquivo cru,
  sem ele, e o painel guarda o do instantâneo. */
function catalogo(e) { return obj(e.catalogo_light) || obj(BOOT && BOOT.catalogo_light) || {}; }
/* Só chave própria: um id ou resultado adulterado ('constructor') não traz o protótipo. */
const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k) ? o[k] : undefined;
const RES = { conforme: ['conf', 'conforme'], nao_conforme: ['nconf', 'não conforme'], nao_se_aplica: ['nsa', 'não se aplica'] };

/* Onde o revisor está: o primeiro mandato sem voto (a ordem é a do rito), depois a síntese. */
function andamento(e) {
 const m = {}; lista(e.cadeiras).forEach(c => { if (typeof c.id === 'string') m[c.id] = c; });
 const feitos = MAND.filter(d => votou(m[d.id])).length;
 const prox = MAND.find(d => !votou(m[d.id]));
 const sintese = votou(obj(e.relator));
 const aberto = feitos > 0 || e.fase !== 'distribuicao';
 return { m, feitos, prox: fimDe(e) ? null : prox, sintese, aberto };
}
function rotRes(v) { return v === 'aprovar' ? 'conforme' : v === 'devolver' ? 'devolve' : ''; }
function chip(v, pend) {
 return v === 'aprovar' ? '<span class="voto aprovar">Conforme</span>' : v === 'devolver'
  ? '<span class="voto devolver">Devolve</span>' : '<span class="voto pend">' + pend + '</span>';
}
const PENSA = ' <span class="think"><i></i><i></i><i></i></span>';

function janela(e, a) {
 const rev = obj(e.revisor) || {};
 const id = txt(rev.agente_id).trim(), mod = txt(rev.modelo_pedido).trim();
 let agora;
 if (fimDe(e)) agora = 'revisão concluída: ' + (e.fase === 'aprovado' ? 'aprovada' : 'devolvida');
 else if (!a.aberto) agora = 'aguardando o despacho do revisor' + PENSA;
 else if (a.prox) agora = 'consultando o mandato ' + a.prox.nome + PENSA;
 else if (!a.sintese) agora = 'lavrando a síntese do relator' + PENSA;
 else agora = 'aguardando a proclamação' + PENSA;
 let h = '<div class="lt-win"><div class="lt-bar"><i></i><i></i><i></i><span>Revisor único · Revisão Light</span></div>' +
  '<div class="lt-body"><div>agente <b>' + (id ? esc(id) : 'a despachar') + '</b> · modelo pedido <b>' +
  (mod ? esc(mod) : '—') + '</b>' + (e.isolamento && e.isolamento.modo === 'serial' ? ' · em série, pelo próprio agente' : '') +
  '</div><div class="lt-agora">› ' + agora + '</div>';
 MAND.concat([{ id: 'relator', nome: 'Síntese do relator' }]).forEach(d => {
  const v = d.id === 'relator' ? obj(e.relator) : a.m[d.id];
  const n = d.id === 'relator' ? 0 : lista(v && v.itens_conferidos).length;
  const cls = votou(v) ? (v.voto === 'aprovar' ? ' ok' : ' no') : (a.prox && a.prox.id === d.id) ||
   (d.id === 'relator' && a.aberto && !a.prox && !fimDe(e)) ? ' on' : '';
  const est = votou(v) ? rotRes(v.voto) + (n ? ' · ' + n + ' itens' : '') : cls ? 'em análise' : 'aguardando';
  h += '<div class="lt-li' + cls + '"><span>' + (votou(v) ? '✓' : cls ? '›' : '·') + '</span><span>' +
   d.nome + ' — ' + est + '</span></div>';
 });
 return h + '</div></div>';
}

function render() {
 try {
 const e = obj(estado) ? estado : { fase: '', cadeiras: [], eventos: [] };
 const semDados = !obj(estado);
 if (semDados) online = false;
 e.cadeiras = lista(e.cadeiras); e.eventos = lista(e.eventos); e.relator = obj(e.relator) || {};
 const fim = fimDe(e), a = andamento(e), cat = catalogo(e);
 const t = document.getElementById('titulo');
 if (t) t.innerHTML = 'Revisão Light <small>· Conselho Revisor</small>';
 document.getElementById('peca').innerHTML = '<b>Peça:</b> ' + esc(e.peca || '—');
 const qd = quando(instante(e));
 document.getElementById('ciclo').textContent = 'Ciclo ' + (txt(e.ciclo) || '—') + (qd ? ' · ' + qd : '');
 const cic = document.getElementById('ciclos'); cic.style.display = 'none'; cic.innerHTML = '';
 const rb = document.getElementById('revbar'); rb.style.display = 'none'; rb.innerHTML = '';
 // stepper: a trilha do revisor, um passo por mandato
 const idx = fim ? 6 : !a.aberto ? 0 : a.prox ? 1 + MAND.indexOf(a.prox) : 5;
 document.getElementById('steps').className = 'steps lt-steps';
 document.getElementById('cards').className = 'cards lt-cards';
 document.getElementById('steps').innerHTML = PASSOS.map((p, i) => {
  const v = i >= 1 && i <= 4 ? a.m[p[0]] : i === 5 ? e.relator : null;
  let cls = 'step' + (i < idx ? ' done' : i === idx ? ' on' : '') + (votou(v) && v.voto === 'devolver' ? ' lt-dev' : '');
  let rot = p[1];
  if (i === 6 && fim) { cls += e.fase === 'aprovado' ? ' fim-ok' : ' fim-no'; rot = e.fase === 'aprovado' ? 'Aprovada' : 'Devolvida'; }
  return '<div class="' + cls + '">' + rot + '</div>';
 }).join('');
 const cena = document.getElementById('cena');
 if (cena) cena.innerHTML = janela(e, a);
 const ban = document.getElementById('banner');
 ban.style.display = 'block';
 if (!semDados && e.variante !== 'light') {
  ban.className = 'banner pend';
  ban.textContent = 'Esta sessão não é da Revisão Light: gere de novo o painel pelo conversor';
 } else if (fim) {
  ban.className = 'banner ' + (e.fase === 'aprovado' ? 'ok' : 'dev');
  ban.textContent = e.fase === 'aprovado' ? 'REVISÃO LIGHT aprovada' : 'REVISÃO LIGHT devolvida';
 } else { ban.className = 'banner lt'; ban.textContent = FAIXA; }
 // a faixa fica no banner enquanto a revisão anda; na decisão, o banner dá o resultado e ela desce
 let html = fim ? '<div class="lt-faixa">' + FAIXA + '</div>' : '';
 MAND.forEach(d => {
  const v = a.m[d.id] || {}, feito = votou(v), agora = a.prox && a.prox.id === d.id && a.aberto;
  const its = lista(v.itens_conferidos), porId = {};
  its.forEach(it => { porId[txt(it.id)] = it; });
  const base = Array.isArray(cat[d.id]) ? cat[d.id] : [];
  const ids = base.map(x => txt(x && x[0])).filter(Boolean);
  its.forEach(it => { if (ids.indexOf(txt(it.id)) < 0) ids.push(txt(it.id)); });
  const texto = {}; base.forEach(x => { if (x) texto[txt(x[0])] = txt(x[1]); });
  html += '<div class="card" style="border-top-color:' + d.cor + '"><h3>Mandato — ' + d.nome +
   (ids.length ? ' <small>' + ids.length + ' itens</small>' : '') + '</h3>' +
   '<div class="st">' + (feito ? rotRes(v.voto) : agora ? 'em análise' : 'aguardando') + (agora ? PENSA : '') + '</div>' +
   chip(feito ? v.voto : null, agora ? 'em análise' : 'aguardando') +
   '<div class="arg">' + esc(feito ? v.fundamentacao : '') + '</div>';
  if (ids.length) {
   html += '<div class="lt-its">' + ids.map(i => {
    const it = own(porId, i), r = it && own(RES, it.resultado);
    return '<div class="lt-it"><span class="n">' + esc(i) + '</span><span>' + esc(own(texto, i) || '') + '</span>' +
     '<span class="r ' + (r ? r[0] : 'pend') + '">' + (r ? r[1] : 'a conferir') + '</span>' +
     (it && txt(it.trecho) ? '<span class="t">' + esc(it.trecho) + '</span>' : '') + '</div>';
   }).join('') + '</div>';
  }
  html += '</div>';
 });
 const r = e.relator, rs = votou(r), ranal = a.aberto && !a.prox && !rs && !fim;
 html += '<div class="card relator"><h3>Relator — síntese da Revisão Light</h3>' +
  (fim ? '<span class="voto ' + (e.fase === 'aprovado' ? 'aprovar' : 'devolver') + '">' +
   (e.fase === 'aprovado' ? 'REVISÃO LIGHT aprovada' : 'REVISÃO LIGHT devolvida') + '</span>'
   : chip(rs ? r.voto : null, ranal ? 'em análise' : 'fecha depois dos quatro mandatos')) +
  '<div class="arg">' + esc(rs ? r.fundamentacao : 'Fecha a revisão depois dos quatro mandatos. Qualquer mandato, ou a síntese, que devolva devolve a peça.') + '</div></div>';
 if (e.fase === 'devolvido') {
  html += '<div class="lt-oferta">A divergência vai ao advogado, que decide entre corrigir e submeter de novo ou pedir o Conselho completo (cinco julgadores).</div>';
 } else if (e.risco === 'alto') {
  html += '<div class="lt-oferta">Peça de risco alto: antes do protocolo, o advogado pode pedir o Conselho completo (cinco julgadores).</div>';
 }
 document.getElementById('cards').innerHTML = html;
 document.getElementById('ata').innerHTML = e.eventos.slice().reverse().map(ev =>
  '<div class="ev"><span class="h">' + esc(hora(ev.em) || ev.hora) + '</span>' +
  '<span class="q ' + classeQuem(ev.quem) + '">' + esc(ev.quem) + '</span> — ' + esc(semNome(ev.quem, ev.texto)) + '</div>'
 ).join('') || '<div class="ev">Nenhum evento registrado ainda.</div>';
 const meta = document.getElementById('meta');
 if (online) meta.textContent = 'ao vivo';
 else if (semDados) meta.textContent = 'sem sessão registrada';
 else meta.textContent = (qd ? 'instantâneo de ' + qd : 'instantâneo sem horário registrado') +
  (fim ? ' — decisão' : e.fase ? ' — revisão em andamento' : '');
 document.getElementById('pulse').className = 'pulse' + (online ? '' : ' off');
 } catch (err) {
  document.getElementById('meta').textContent = 'estado ilegível';
  document.getElementById('pulse').className = 'pulse off';
 }
}
const TEM_COWORK = typeof window !== 'undefined' && !!window.cowork && typeof window.cowork.callMcpTool === 'function';
async function poll() {
 if (!TEM_COWORK) { online = false; render(); return; }
 try {
  const r = await window.cowork.callMcpTool('mcp__workspace__bash', { command: POLL_EXATO || POLL, timeout_ms: 20000 });
  const t = (r && r.content || []).map(c => c.text || '').join('').trim();
  if (r && r.isError) throw new Error(t);
  online = false;
  if (t && t !== 'NOFILE') {
   estado = JSON.parse(t.slice(t.indexOf('{')));
   online = true;
   try { localStorage.setItem('conselho_light_ultimo', JSON.stringify(estado)); } catch (e3) {}
  }
 } catch (err) {
  online = false;
  if (!estado) { try { const s = localStorage.getItem('conselho_light_ultimo'); if (s) estado = JSON.parse(s); } catch (e2) {} }
 }
 render();
}
const RODAPE = 'REVISÃO LIGHT: um único revisor percorre em série os quatro mandatos (Mérito, Coerência, Escrita, Conformidade) e fecha com a síntese do relator; qualquer devolução devolve a peça. Não é deliberação colegiada. A decisão de protocolar é sempre do advogado.';
const AUTO_REFRESH = TEM_COWORK && (!BOOT || !!STATE_PATH) && !(BOOT && BOOT.publicado_pseudonimizado);
document.getElementById('foot').textContent = (AUTO_REFRESH
 ? 'Acompanhamento ao vivo: este painel se atualiza a cada 5 segundos durante a revisão. '
 : 'Retrato do último estado registrado: este painel mostra a revisão como estava quando foi gerado e não se atualiza sozinho. ') + RODAPE;
render();
if (AUTO_REFRESH) { setInterval(poll, 5000); poll(); }
