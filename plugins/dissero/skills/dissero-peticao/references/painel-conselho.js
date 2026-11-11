
const CAD = [
 { id:'merito',       nome:'Des. Vogal — Mérito',       curto:'MÉRITO',    cor:'#3b5fa3', luz:'#5d82c9', x: 104 },
 { id:'coerencia',    nome:'Des. Vogal — Coerência',    curto:'COERÊNCIA', cor:'#2a8a7c', luz:'#46ab9c', x: 316 },
 { id:'escrita',      nome:'Des. Vogal — Escrita',      curto:'ESCRITA',   cor:'#7a4fa3', luz:'#9a70c4', x: 528 },
 { id:'conformidade', nome:'Des. Vogal — Conformidade', curto:'CONFORMIDADE',  cor:'#a3793b', luz:'#c49a5c', x: 740 }
];
const PASSOS = [['distribuicao','Distribuição'],['debate','Debate'],['votacao','Votação'],['apreciacao','Proclamação'],['fim','Decisão']];
/* Busca do estado no Cowork quando o painel não traz o caminho: o arquivo mais novo de
  /sessions/<sessão>/mnt (CONSELHO_STATUS.json ou CONSELHO_STATUS_<cap>.json). O `ls -t` só roda se o
  find achou algo: sem argumento ele listaria a pasta corrente, e o painel exibiria um JSON
  qualquer como se fosse a sessão. */
const POLL = 'l=$(find /sessions/*/mnt -maxdepth 3 \\( -name CONSELHO_STATUS.json -o -name "CONSELHO_STATUS_*.json" \\) 2>/dev/null); f=; ' +
 'if [ -n "$l" ]; then set -f; IFS=\'\n\'; f=$(ls -t $l 2>/dev/null | head -1); fi; ' +
 'if [ -n "$f" ]; then cat "$f"; else echo NOFILE; fi';
const BOOT = /*ESTADO_INLINE*/ null; // modo inline: substituir 'null' pelo JSON do estado
const STATE_PATH = /*STATE_PATH*/ null; // caminho EXATO do estado: o painel_fragmento.py o injeta junto com o BOOT
/* aspas simples do sh: o caminho vai ao `cat` como um argumento só, com espaço ou aspas dentro */
function shq(s) { return "'" + String(s).replace(/'/g, "'\\''") + "'"; }
const POLL_EXATO = STATE_PATH ? 'f=' + shq(STATE_PATH) + '; if [ -f "$f" ]; then cat "$f"; else echo NOFILE; fi' : null;
/* `online` = conexão VIVA, que só o poll do Cowork estabelece. Estado embutido é INSTANTÂNEO: um
  arquivo aberto dias depois não se declara "ao vivo". */
let estado = BOOT, tick = 0, online = false;

/* ESCAPE. Todo valor do estado que entra em innerHTML passa por esc(): o estado é DADO (voto que
  cita documento da parte contrária, ata), nunca marcação. O json_para_script do conversor
  protege o código-fonte; esc() protege o DOM, onde uma tag de imagem com onerror vinda da
  fundamentação executaria. As outras funções desta seção devolvem só vocabulário fixo. */
/* texto só de primitivo: objeto no lugar de texto (estado fora do contrato) sai vazio */
function txt(v) { const t = typeof v; return (t === 'string' || t === 'number' || t === 'boolean') ? String(v) : ''; }
function esc(v) {
 return txt(v).replace(/[&<>"']/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}
function classeVoto(v) { return (v === 'aprovar' || v === 'devolver') ? v : 'pend'; }
function rotVoto(v) { return v === 'aprovar' ? 'Aprovar' : v === 'devolver' ? 'Devolver' : 'aguardando voto'; }
function chipVoto(v) { return '<span class="voto ' + classeVoto(v) + '">' + rotVoto(v) + '</span>'; }
/* quem da ata como CLASSE: só [a-z0-9-] ('Mérito' -> 'merito', 'Art. 942 (1)' -> 'art-942-1') */
function classeQuem(q) {
 let s = txt(q);
 if (s.normalize) s = s.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
 return s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}
/* O texto automático da ata já abre com o nome ("Mérito votou APROVAR"); ao lado do selo do
  assento, o nome sai do texto para a linha não o repetir, só quando vem seguido de ":" ou espaço
  e de mais texto ("Relatora…" e "Méritos…" ficam inteiros; o placar leve faz o mesmo). Devolve
  TEXTO: quem chama escapa. */
function semNome(q, t) {
 const qm = txt(q), tx = txt(t), r = tx.slice(qm.length);
 return (qm && tx.indexOf(qm) === 0 && /^[:\s]+\S/.test(r)) ? r.replace(/^[:\s]+/, '') : tx;
}
/* Carimbo ISO -> hora NO FUSO DE QUEM OLHA. O produtor grava com fuso (…T10:33:59-03:00; na
  nuvem, +00:00); carimbo sem fuso (o --ts antigo) é lido como hora local, que é o que ele
  sempre quis dizer. Carimbo ilegível devolve '' (só dígitos saem daqui). */
function p2(n) { return (n < 10 ? '0' : '') + n; }
function quando(iso) {
 const d = txt(iso) ? new Date(txt(iso)) : null;
 if (!d || isNaN(d.getTime())) return '';
 return p2(d.getDate()) + '/' + p2(d.getMonth() + 1) + ' ' + p2(d.getHours()) + ':' + p2(d.getMinutes());
}
function hora(iso) { const q = quando(iso); return q ? q.slice(6) : ''; }
/* De quando é o que está na tela: `atualizado` (o produtor grava a cada movimento) ou, em estado
  antigo sem ele, o carimbo do último andamento da ata. */
function instante(e) {
 if (quando(e.atualizado)) return e.atualizado;   // ilegível (--ts fora de ISO) cai na ata
 const evs = (e.eventos || []).filter(ev => ev && quando(ev.em));
 return evs.length ? evs[evs.length - 1].em : '';
}
/* O retrato inline diz de quando é e se a sessão ainda anda ou já decidiu. Sessão aberta nunca
  aparece como encerrada: era o que o rótulo antigo dizia de todo estado sem `atualizado`. */
function rotuloInstante(e) {
 const q = quando(instante(e));
 const fimDec = e.fase === 'aprovado' || e.fase === 'devolvido';
 return (q ? 'instantâneo de ' + q : 'instantâneo sem horário registrado') +
     (fimDec ? ' — decisão' : e.fase ? ' — sessão em andamento' : '');
}

/* normaliza(): deriva os campos de exibição (status, argumento, fundamento) dos canônicos
  (voto/fundamentacao/fase) QUANDO ausentes, para o painel desenhar o arquivo RICO do
  conselho_sessao.py e o FINO só do gate. Idempotente. O placar sai de contagem(). */
/* forma(): estado fora do contrato (objeto no lugar de lista, nulo na lista) não derruba o render,
  que ficava em "conectando…" (medido). */
function obj(v) { return v && typeof v === 'object' && !Array.isArray(v) ? v : null; }
function lista(v) { return Array.isArray(v) ? v.filter(obj) : []; }
function forma(e) {
 e.cadeiras = lista(e.cadeiras);
 e.eventos = lista(e.eventos);
 e.relator = obj(e.relator) || {};
 e.historico = obj(e.historico) || {};
 if (e.ciclos !== undefined) e.ciclos = lista(e.ciclos);
 const art = obj(e.art942);
 if (art) { art.votos_extra = lista(art.votos_extra); art.convocados = lista(art.convocados); }
 e.art942 = art;
 return e;
}
function normaliza(e) {
 if (!obj(e)) return e;
 forma(e);
 e.cadeiras.forEach(c => {
  if (!c.status) c.status = c.voto ? 'votou' : '—';
  // sem voto ainda, o que há para mostrar é o argumento do DEBATE (campo próprio,
  // gravado pelo `cadeira --status … --fundamentacao …`).
  if (!c.argumento) c.argumento = c.fundamentacao || c.argumento_debate || '';
 });
 const r = e.relator;
 if (!r.status) r.status = (e.fase === 'aprovado' || e.fase === 'devolvido' || r.voto) ? 'decidiu' : 'aguardando';
 if (!r.fundamento) r.fundamento = r.fundamentacao || '';
 return e;
}
const VOTOS = ['aprovar', 'devolver'];
/* Quem reviu o voto (art. 942, § 2º) leva o voto_anterior, diferente do voto. */
function revisou(v) { return VOTOS.indexOf(v.voto_anterior) >= 0 && VOTOS.indexOf(v.voto) >= 0 && v.voto !== v.voto_anterior; }
const reab = e => lista(e.eventos).some(x => x.tipo === 'reabertura');
function porId(e) { const m = {}; (e.cadeiras || []).forEach(c => { if (typeof c.id === 'string') m[c.id] = c; }); return m; }
/* Placar contado dos votos, nunca o declarado (4×1 com 6×1 na turma, medido). Antes da
  proclamação, os vogais, o relator e a ampliação que votou. Na decisão, a regra do gate e do
  `proclamar`: a ampliação conta sem unanimidade ou reaberta, e só os dois primeiros votos válidos. */
function contagem(e) {
 let a = 0, d = 0;
 const m = porId(e), b = CAD.map(cd => (m[cd.id] || {}).voto).concat([(e.relator || {}).voto])
  .map(v => VOTOS.indexOf(v) < 0 ? null : v);
 const x = (e.fase === 'aprovado' || e.fase === 'devolvido')
  ? (b.every(v => v === b[0]) && !reab(e) ? [] : lista((e.art942 || {}).votos_extra).filter(votoValido).slice(0, 2).map(v => v.voto))
  : assentos942(e.art942).map(s => s.st === 'votou' ? s.v.voto : null);
 b.concat(x).forEach(v => { if (v === 'aprovar') a++; else if (v === 'devolver') d++; });
 return { a, d };
}
/* assentos da ampliação: os que votaram e os convocados sem voto, na ordem de `novos`, que é a do
  número da ata (Art. 942 (n)); o 2º convocado pode votar antes do 1º */
function assentos942(art) {
 art = obj(art) || {};
 const extras = lista(art.votos_extra);
 const votados = extras.map(v => txt(v.assento)).filter(Boolean);
 const ordem = Array.isArray(art.novos) ? art.novos.map(txt) : [];
 const pos = s => { const i = ordem.indexOf(txt(s.v.assento)); return i < 0 ? ordem.length : i; };
 return extras.map(v => ({ v, st: VOTOS.indexOf(v.voto) >= 0 ? 'votou' : 'aguardando' }))
  .concat(lista(art.convocados).filter(c => votados.indexOf(txt(c.assento)) < 0)
   .map(c => ({ v: c, st: c.status === 'debatendo' ? 'em debate' : 'em análise' })))
  .map((s, i) => [pos(s), i, s]).sort((x, y) => x[0] - y[0] || x[1] - y[1]).map(x => x[2]);
}
/* o que falta para a proclamação valer, pela regra do conselho_gate.py (cinco votos; a turma sem o
  autor, um agente por assento e, em risco alto, subagentes; sem unanimidade, os dois do art. 942),
  ou o resultado proclamado contra os votos (estado antigo ou escrito à mão; devolvida se devolver
  >= aprovar). Só na decisão. O id que não é texto não conta, como no gate. */
function sid(v) { return typeof v === 'string' ? v.trim() : ''; }
function votoValido(v) { return !!v && VOTOS.indexOf(v.voto) >= 0 && !!sid(v.agente_id) && !!txt(v.fundamentacao).trim(); }
function pendencia(e) {
 const m = porId(e);
 const faltam = CAD.filter(cd => !votoValido(m[cd.id])).map(cd => cd.curto.charAt(0) + cd.curto.slice(1).toLowerCase());
 if (!votoValido(e.relator)) faltam.push('Relator');
 if (faltam.length) return 'Turma incompleta: falta o voto de ' + faltam.join(', ');
 const base = CAD.map(cd => m[cd.id]).concat([e.relator]), un = base.every(v => v.voto === base[0].voto) && !reab(e);
 const art = obj(e.art942) || {}, ext = lista(art.votos_extra).filter(votoValido);
 const ids = base.concat(un ? [] : ext.slice(0, 2)).map(v => sid(v.agente_id));
 const inv = ids.indexOf(sid(e.autor_id)) >= 0 ? 'autor entre os votantes' : new Set(ids).size < ids.length ? 'agente em dois assentos'
  : e.risco === 'alto' && (obj(e.isolamento) || {}).modo !== 'subagentes' ? 'modo serial em risco alto' : '';
 if (inv) return 'Turma inválida: ' + inv;
 if (!un && (!art.acionado || ext.length < 2))
  return 'Ampliação do art. 942 pendente: votação não unânime sem os dois votos da ampliação';
 const ct = contagem(e);
 return (ct.d >= ct.a ? 'devolvido' : 'aprovado') === e.fase ? '' : 'Resultado proclamado diverge dos votos: ' + ct.a + '×' + ct.d;
}
if (BOOT) normaliza(estado);
// vista = estado ATUALMENTE EXIBIDO (ao vivo por padrão; um snapshot do histórico ao rever uma
// fase). revendo = chave da fase em revisão (null = ao vivo). Clicar num passo troca a vista.
let vista = estado, revendo = null;
/* cicloVendo = índice em estado.ciclos[] do ciclo ARQUIVADO em exibição (null = o corrente), que o
  `novo-ciclo` preserva. */
let cicloVendo = null;
/* base() = o "estado" de onde saem stepper, histórico e ata. Para o ciclo corrente é o
  próprio `estado`; para um arquivado, o registro de `ciclos[]`, que tem a mesma forma
  (cadeiras/relator/historico/eventos), com o autor, o risco e o isolamento da sessão. */
function base() {
 if (cicloVendo === null) return estado;
 const a = ((estado && estado.ciclos) || [])[cicloVendo];
 return a ? normaliza(JSON.parse(JSON.stringify(Object.assign({ autor_id: estado.autor_id, risco: estado.risco,
       isolamento: estado.isolamento }, a, { ciclo: a.ciclo,
       peca: a.peca || (estado || {}).peca, atualizado: a.encerrado_em || '' })))) : estado;
}
function mostrarCiclo(i) {
 cicloVendo = (i === null || i === undefined) ? null : i;
 revendo = null;
 vista = base();
 render();
}
function stepKey(fase) { return (fase === 'aprovado' || fase === 'devolvido') ? 'fim' : fase; }
function mostrarFase(key) {
 const b = base();
 const snap = ((b && b.historico) || {})[key];
 if (!snap) return;                         // fase ainda não alcançada → não faz nada
 revendo = key;
 /* normaliza() TAMBÉM na vista revista (o snapshot não tem os campos de exibição); cópia
   profunda porque ela muta. O agente_id, que o retrato não guarda, vem do registro deste ciclo
   por assento: a pendência da decisão revista sai do retrato (o registro reaberto, ou o ciclo
   seguinte trazido pelo poll, já não é a decisão revista). */
 /* o snapshot pode não guardar a ampliação, que só existe da apreciação em diante: a corrente
   vazaria votos para o debate e a votação */
 const amp = snap.art942 !== undefined ? snap.art942 : (key === 'apreciacao' || key === 'fim') ? b.art942 : null;
 const ids = porId(b);
 vista = normaliza(Object.assign({}, b, {
  fase: snap.fase,
  cadeiras: JSON.parse(JSON.stringify(snap.cadeiras || [])).map(c => Object.assign({ agente_id: (ids[c && c.id] || {}).agente_id }, c)),
  relator: Object.assign({ agente_id: (b.relator || {}).agente_id }, JSON.parse(JSON.stringify(snap.relator || {}))),
  art942: JSON.parse(JSON.stringify(amp || null)),
  eventos: (b.eventos || []).slice(0, snap.eventos_len || 0) }));
 render();
}
function voltarAoVivo() { revendo = null; vista = base(); render(); }

/* ---------- sprites ----------
  Mundo de 960x380 e figuras de 32x36 pixels de arte (cabelo em duas camadas, olhos, sombra
  de nariz, boca e as bandas brancas do peito da beca). A arte tem essa resolução para não
  virar borrão quando o painel ocupa a largura inteira da tela. */
/* Dois CORTES, não um desenho recolorido: o cabelo longo desce pelos lados do rosto até os
  ombros, e por isso ocupa colunas que no curto são vazias. Mesma cabeça, mesmo corpo. */
const FIG_CURTO = [
 '............HHHHHHHH............',
 '..........HHHHHHHHHHHH..........',
 '.........HHHHHHHHHHHHHH.........',
 '........HHHHHHHHHHHHHHHH........',
 '........HHHHHHHHHHHHHHHH........',
 '........HHHFFFFFFFFFFHHH........',
 '........HhFFFFFFFFFFFFhH........',
 '.........FFFFFFFFFFFFFF.........',
 '.........FFFFFFFFFFFFFF.........',
 '.........FFooFFFFFFooFF.........',
 '.........FFooFFFFFFooFF.........',
 '.........FFFFFFFFFFFFFF.........',
 '.........FFFFFfffFFFFFF.........',
 '.........FFFFFFFFFFFFFF.........',
 '..........FFFFffffFFFF..........',
 '..........FFFFFFFFFFFF..........',
 '...........FFFFFFFFFF...........',
 '............FFFFFFFF............',
 '...........WWWWWWWWWW...........',
 '.........rRRWWWWWWWWRRr.........',
 '........rRRRRWWWWWWRRRRr........',
 '.......rRRRRRWWWWWWRRRRRr.......',
 '......rRRRRRRWWWWWWRRRRRRr......',
 '......rRRRRRRRWWWWRRRRRRRr......',
 '.....rRRRRRRRRWWWWRRRRRRRRr.....',
 '.....rRRRRRRRRRWWRRRRRRRRRr.....',
 '.....rRRRRRRRRRRRRRRRRRRRRr.....',
 '....rRRRRRRRRRRRRRRRRRRRRRRr....',
 '....rRRRRRRRRRRRRRRRRRRRRRRr....',
 '....rRRRRRRRRRRRRRRRRRRRRRRr....',
 '....rRRRRRRRRRRRRRRRRRRRRRRr....',
 '....rRRRRRRRRRRRRRRRRRRRRRRr....',
 '....rRRRRRRRRRRRRRRRRRRRRRRr....',
 '...rrRRRRRRRRRRRRRRRRRRRRRRrr...',
 '...rrRRRRRRRRRRRRRRRRRRRRRRrr...',
 '...rrrrrrrrrrrrrrrrrrrrrrrrrr...'
];
const FIG_LONGO = [
 '............HHHHHHHH............',
 '..........HHHHHHHHHHHH..........',
 '.........HHHHHHHHHHHHHH.........',
 '........HHHHHHHHHHHHHHHH........',
 '.......HHHHHHHHHHHHHHHHHH.......',
 '.......HHHHFFFFFFFFFFHHHH.......',
 '.......HHhFFFFFFFFFFFFhHH.......',
 '.......HHFFFFFFFFFFFFFFHH.......',
 '.......HHFFFFFFFFFFFFFFHH.......',
 '.......HHFFooFFFFFFooFFHH.......',
 '.......HHFFooFFFFFFooFFHH.......',
 '.......HHFFFFFFFFFFFFFFHH.......',
 '.......HHFFFFFfffFFFFFFHH.......',
 '.......HHFFFFFFFFFFFFFFHH.......',
 '.......HHhFFFFffffFFFFhHH.......',
 '.......HHhFFFFFFFFFFFFhHH.......',
 '.......HHhhFFFFFFFFFFhhHH.......',
 '.......HHHhhFFFFFFFFhhHHH.......',
 '.......HHHHWWWWWWWWWWHHHH.......',
 '.......HHrRRWWWWWWWWRRrHH.......',
 '......HHrRRRRWWWWWWRRRRrHH......',
 '......HrRRRRRWWWWWWRRRRRrH......',
 '......rRRRRRRWWWWWWRRRRRRr......',
 '......rRRRRRRRWWWWRRRRRRRr......',
 '.....rRRRRRRRRWWWWRRRRRRRRr.....',
 '.....rRRRRRRRRRWWRRRRRRRRRr.....',
 '.....rRRRRRRRRRRRRRRRRRRRRr.....',
 '....rRRRRRRRRRRRRRRRRRRRRRRr....',
 '....rRRRRRRRRRRRRRRRRRRRRRRr....',
 '....rRRRRRRRRRRRRRRRRRRRRRRr....',
 '....rRRRRRRRRRRRRRRRRRRRRRRr....',
 '....rRRRRRRRRRRRRRRRRRRRRRRr....',
 '....rRRRRRRRRRRRRRRRRRRRRRRr....',
 '...rrRRRRRRRRRRRRRRRRRRRRRRrr...',
 '...rrRRRRRRRRRRRRRRRRRRRRRRrr...',
 '...rrrrrrrrrrrrrrrrrrrrrrrrrr...'
];
/* Brasão da balança da Justiça, no painel da parede do plenário. */
const BRASAO = [
 '...................GG...................',
 '..................GGGG..................',
 '..................GGGG..................',
 '...................GG...................',
 '....GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG....',
 '....GggGGGGGGGGGGGGGGGGGGGGGGGGGGggG....',
 '....G..............GG..............G....',
 '....G..............GG..............G....',
 '..GGGGG............GG............GGGGG..',
 '.GGGGGGG...........GG...........GGGGGGG.',
 '.gGGGGGg...........GG...........gGGGGGg.',
 '..ggggg............GG............ggggg..',
 '...................GG...................',
 '...................GG...................',
 '...................GG...................',
 '...................GG...................',
 '...................GG...................',
 '..................GGGG..................',
 '.................GGGGGG.................',
 '................GGGGGGGG................',
 '..............GGGGGGGGGGGG..............',
 '............GGGGGGGGGGGGGGGG............'
];
function sprite(ctx, arte, ox, oy, cores, bob, esc) {
 const e = esc || 1;                       // cada pixel da arte vira um bloco e x e
 for (let y = 0; y < arte.length; y++) {
  const linha = arte[y];
  for (let x = 0; x < linha.length; x++) {
   const k = linha[x], c = cores[k];
   if (c) R(ctx, ox + x*e, oy + y*e + (bob || 0), e, e, c);
  }
 }
}
const FIG_ESC = 2;                          // escala INTEIRA: 1,5x deixaria blocos desiguais
const FIG_W = 32 * FIG_ESC, FIG_H = 36 * FIG_ESC;
/* Cada assento é uma PESSOA, não o mesmo boneco recolorido: tom de pele, cabelo, olhos e
  corte próprios, homens e mulheres. Cinco figuras idênticas apagariam a ideia de colegiado. */
const PESSOAS = {
 relator:      { pele:'#c9926a', peleSombra:'#a9764f', cabelo:'#6f6c67', luzCabelo:'#8f8c86', olho:'#2b2118', longo:true  },
 merito:       { pele:'#eccfa9', peleSombra:'#d4b189', cabelo:'#3a2a1a', luzCabelo:'#5a4228', olho:'#1d2433', longo:false },
 coerencia:    { pele:'#8d5a34', peleSombra:'#734427', cabelo:'#191310', luzCabelo:'#332a20', olho:'#231a12', longo:true  },
 escrita:      { pele:'#e6bd92', peleSombra:'#c99b6f', cabelo:'#7a3b1e', luzCabelo:'#9c5730', olho:'#33251a', longo:false },
 conformidade: { pele:'#a8703f', peleSombra:'#8a5a30', cabelo:'#241f26', luzCabelo:'#3f3744', olho:'#1f1a16', longo:true  }
};
const PESSOA_PADRAO = PESSOAS.merito;
function fig(ctx, ox, oy, cor, luz, bob, pessoa) {
 /* a luz entra pela direita: a metade direita da beca usa o tom claro */
 const p = pessoa || PESSOA_PADRAO;
 const arte = p.longo ? FIG_LONGO : FIG_CURTO;
 const C = { H:p.cabelo, h:p.luzCabelo, F:p.pele, f:p.peleSombra, o:p.olho,
       R:cor, r:shade(cor,-30), W:'#f7f7f4', w:'#d9d9d2' };
 const e = FIG_ESC;
 for (let y = 0; y < arte.length; y++) {
  const linha = arte[y];
  for (let x = 0; x < 32; x++) {
   const k = linha[x];
   if (C[k]) R(ctx, ox + x*e, oy + y*e + (bob || 0), e, e, (k === 'R' && x > 19) ? luz : C[k]);
  }
 }
}
function brasao(ctx, ox, oy, esc) {
 sprite(ctx, BRASAO, ox, oy, { G:'#d8b86a', g:'#8f7434' }, 0, esc || 1);
}
function shade(hex, d) {
 const n = parseInt(hex.slice(1),16), f = v => Math.max(0,Math.min(255,v+d));
 return '#'+[(n>>16)&255,(n>>8)&255,n&255].map(v=>f(v).toString(16).padStart(2,'0')).join('');
}
/* traco diagonal em blocos, com espessura — e o que da forma ao V do certo e ao X do errado
  sem depender de antialias, que quebraria a linguagem de pixel do resto da cena */
function diag(ctx, x, y, passos, dx, dy, esp, cor) {
 for (let i = 0; i < passos; i++) R(ctx, x + i*dx, y + i*dy, esp, esp, cor);
}
/* ---------- resolução: arte em pixel crocante, TIPOGRAFIA nítida ----------
  O backing store tem o tamanho REAL de exibição (× devicePixelRatio), o mundo é descrito em
  MUNDO_W x MUNDO_H e a escala entra no desenho: sprites snapados ao pixel do dispositivo, texto
  rasterizado no tamanho final. Esticar o canvas por CSS borraria nomes e bonecos. */
let S = 1;                                  // unidades do mundo -> pixels do dispositivo
const MUNDO_W = 960, MUNDO_H = 380;
function px(v) { return Math.round(v * S); }
/* R() snapa em DEVICE PIXELS: `px(x+w) - px(x)` em vez de `px(w)` evita que o arredondamento
  independente de origem e tamanho abra fresta de subpixel entre blocos vizinhos. */
function R(ctx,x,y,w,h,c){ ctx.fillStyle=c; ctx.fillRect(px(x), px(y), px(x+w)-px(x), px(y+h)-px(y)); }
function texto(ctx, str, x, y, tam, familia, cor, alinha) {
 ctx.fillStyle = cor;
 ctx.font = 'bold ' + (tam * S).toFixed(2) + 'px ' + familia;
 ctx.textAlign = alinha || 'left';
 ctx.fillText(str, px(x), px(y));
}
const ALTURA_MAX = 330;                     // a cena é uma faixa, não um mural
/* Largura do salão EM UNIDADES DE MUNDO, recalculada a cada desenho. Quem manda na escala é a
  ALTURA (a faixa tem teto); a largura sobrando vira mais salão, e não tarja preta. A mobília
  continua descrita num palco de MUNDO_W unidades, que é centrado nesse salão. */
let MUNDO_VISIVEL = MUNDO_W;
function ajustaCanvas(cv) {
 // teto de 3 no DPR: acima disso o ganho visual some e a área de pintura cresce ao quadrado
 const dpr = Math.min(window.devicePixelRatio || 1, 3);
 let larguraCss = cv.parentNode ? cv.parentNode.clientWidth : (cv.clientWidth || MUNDO_W);
 if (!larguraCss) larguraCss = MUNDO_W;
 const alturaCss = Math.min(ALTURA_MAX, larguraCss * MUNDO_H / MUNDO_W);
 S = (alturaCss * dpr) / MUNDO_H;
 MUNDO_VISIVEL = Math.max(MUNDO_W, (larguraCss * dpr) / S);
 const w = Math.round(larguraCss * dpr), h = Math.round(alturaCss * dpr);
 if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; }
 cv.style.width = '100%';
 cv.style.height = alturaCss.toFixed(2) + 'px';
}
function bolha(ctx, x, y) {
 R(ctx,x,y,40,22,'#fdfdfa'); R(ctx,x+2,y+22,8,6,'#fdfdfa');
 R(ctx,x,y,40,2,'#d8d8cf'); R(ctx,x,y+20,40,2,'#d8d8cf');
 const n=(tick%3)+1; for(let i=0;i<n;i++) R(ctx,x+8+i*10,y+10,4,4,'#4a4a4a');
}
/* SELO — medalhão de 30x20 com borda escura, corpo, faixa de brilho no topo e traço GROSSO:
  o V do certo e o X do errado têm 3 unidades de espessura, para continuarem legíveis quando
  a cena encolhe. */
function selo(ctx, x, y, ok) {
 const base = ok ? '#1f8a4c' : '#c23434';
 const borda = shade(base, -34), brilho = shade(base, 26), traco = '#ffffff';
 R(ctx, x+2, y,    26, 20, borda);          // corpo com cantos cortados
 R(ctx, x,   y+2,  30, 16, borda);
 R(ctx, x+3, y+1,  24, 18, base);
 R(ctx, x+1, y+3,  28, 14, base);
 R(ctx, x+4, y+2,  22,  4, brilho);         // brilho no topo
 if (ok) {
  diag(ctx, x+8,  y+9,  4, 1,  1, 3, traco);   // perna curta do V
  diag(ctx, x+11, y+12, 6, 1, -1, 3, traco);   // perna longa
 } else {
  // X: dois traços espelhados de 11x11 que se cruzam no centro do medalhão (15,10). Começar
  // os dois à esquerda e terminar no meio desenhava um "›" (titular, 23/10/2026).
  diag(ctx, x+10, y+5,  9, 1,  1, 3, traco);   // de cima à esquerda para baixo à direita
  diag(ctx, x+10, y+13, 9, 1, -1, 3, traco);   // de baixo à esquerda para cima à direita
 }
}
/* O martelo NÃO carrega estado: 'decidiu' é permanente, e um gesto preso nele viraria pose
  parada. Quem diz que houve decisão são o selo sobre o relator, a faixa abaixo da cena e o
  stepper. Aqui ele é um maço pousado no bloco. */
function martelo(ctx, x, y) {
 R(ctx, x,     y+13, 40,  7, '#412c18');   // bloco de apoio
 R(ctx, x,     y+11, 40,  3, '#6b4a2a');
 R(ctx, x+3,   y+2,  17, 11, '#7d5228');   // maço deitado, cabeça à esquerda
 R(ctx, x+3,   y+2,  17,  3, '#9c6836');
 R(ctx, x+20,  y+5,  18,  5, '#9a7032');   // cabo
 R(ctx, x+20,  y+5,  18,  2, '#b88a44');
}
function desenha() {
 const cv = document.getElementById('cv');
 if (!cv) return;
 ajustaCanvas(cv);                       // backing store = tamanho real de exibicao
 const ctx = cv.getContext('2d');
 ctx.setTransform(1, 0, 0, 1, 0, 0);
 ctx.clearRect(0, 0, cv.width, cv.height);
 // fundo com gradiente em faixas (céu de salão)
 for (let i = 0; i < 38; i++) R(ctx,0,i*10,MUNDO_VISIVEL,10, shade('#1c2336', -Math.floor(i/2)));
 R(ctx,0,296,MUNDO_VISIVEL,84,'#3d2c1c'); R(ctx,0,292,MUNDO_VISIVEL,4,'#241a10');   // piso
 for (let x = 0; x < MUNDO_VISIVEL; x += 64) R(ctx,x,296,32,84,shade('#3d2c1c',6)); // tábuas
 // daqui em diante desenha-se o PALCO (mobília e figuras), centrado no salão
 ctx.setTransform(1, 0, 0, 1, Math.round((MUNDO_VISIVEL - MUNDO_W) / 2 * S), 0);
 // painel da parede com o BRASÃO DA JUSTIÇA: a balança vai a 2x (80x44) e a moldura acompanha.
 R(ctx,404,4,152,98,'#2a2010'); R(ctx,408,8,144,90,'#4a3a22'); R(ctx,416,16,128,74,'#141a2b');
 brasao(ctx, 440, 31, 2);
 const rel = (vista && vista.relator) || {};
 const bobR = rel.status === 'apreciando' ? (tick % 2) : 0;
 // ORDEM: o boneco PRIMEIRO, a bancada DEPOIS. É a bancada que esconde o tronco; desenhado
 // por cima, o boneco pairaria acima do tampo.
 // centro da bancada = 480; a figura tem FIG_W de largura, logo ox = 480 - FIG_W/2
 fig(ctx, 480 - FIG_W/2, 128, '#8c2f2f', '#aa4d4d', bobR, PESSOAS.relator);
 R(ctx,364,188,232,54,'#5a3a1e'); R(ctx,356,184,248,8,'#7a5430'); R(ctx,372,242,216,8,'#33210f');
 R(ctx,380,196,200,4,shade('#5a3a1e',14));
 martelo(ctx, 522, 170);                             // pousado no tampo, dentro da bancada
 if (rel.status === 'apreciando') bolha(ctx, 508, 92);
 if (rel.status === 'decidiu' && rel.voto) selo(ctx, 465, 104, rel.voto === 'aprovar');
 texto(ctx, 'RELATOR', 480, 272, 17, 'Verdana, "Segoe UI", sans-serif', '#e6d3ae', 'center');
 // conselheiros
 const m = {}; lista(vista && vista.cadeiras).forEach(c => { if (typeof c.id === 'string') m[c.id] = c; });
 CAD.forEach(cd => {
  const st = m[cd.id] || {};
  const bob = (st.status === 'analisando' || st.status === 'debatendo') ? (tick % 2) : 0;
  // boneco ANTES da mesa: a mesa cobre o tronco e o vogal fica sentado, não flutuando
  // centro da mesa = cd.x+58 (a mesa vai de cd.x-16 a cd.x+132)
  fig(ctx, cd.x + 58 - FIG_W/2, 256, cd.cor, cd.luz, bob, PESSOAS[cd.id]);
  R(ctx, cd.x-16, 316, 148, 36, '#5a3a1e'); R(ctx, cd.x-20, 312, 156, 6, '#7a5430');
  R(ctx, cd.x+36, 322, 44, 6, '#f2efe4');            // folha centrada na mesa
  if (st.status === 'debatendo' || st.status === 'analisando') bolha(ctx, cd.x+92, 216);
  if (st.status === 'votou' && st.voto) selo(ctx, cd.x+43, 228, st.voto === 'aprovar');
  texto(ctx, cd.curto, cd.x + 56, 372, 15, 'Verdana, "Segoe UI", sans-serif', '#e6d3ae', 'center');
 });
 ctx.setTransform(1, 0, 0, 1, 0, 0);
}
/* ---------- dados e UI ---------- */
// Estado vazio: sem um CONSELHO_STATUS.json real, o painel NÃO encena uma turma deliberando;
// declara que não há sessão registrada. Simular deliberação daria falsa sensação de rigor.
const semSessao = () => ({ peca:'— nenhuma sessão de conselho registrada —', fase:null, ciclo:0, atualizado:'',
 cadeiras: CAD.map(c => ({ id:c.id, papel:'Vogal', status:'—', voto:null, argumento:'Sem sessão registrada.' })),
 relator:{ status:'aguardando', voto:null, resultado:null,
      fundamento:'Nenhuma sessão de julgamento registrada (CONSELHO_STATUS.json ausente). Este painel não simula deliberação.' },
 eventos:[] });
function render() {
 try {                                     // estado que ainda lance não fica em "conectando…"
 const semDados = !obj(vista);
 const e = semDados ? semSessao() : vista;
 if (semDados) online = false;
 document.getElementById('peca').innerHTML = '<b>Peça:</b> ' + esc(e.peca || '—');
 const qd = quando(instante(e));
 document.getElementById('ciclo').textContent = 'Ciclo ' + (txt(e.ciclo) || '—') + (qd ? ' · ' + qd : '');
 // stepper
 const fim = (e.fase === 'aprovado' || e.fase === 'devolvido');
 const idx = fim ? 4 : (semDados ? -1 : Math.max(0, PASSOS.findIndex(p => p[0] === e.fase)));
 /* Faixa de CICLOS: só aparece quando há ciclo arquivado (sessão de ressubmissão). Cada
   pastilha leva ao ciclo inteiro — stepper, cartões e ata daquele ciclo —, que é o que
   permite ao vogal conferir se o defeito que ele apontou no ciclo anterior foi sanado. */
 const arq = (estado && Array.isArray(estado.ciclos)) ? estado.ciclos : [];
 const faixa = document.getElementById('ciclos');
 if (arq.length) {
  faixa.style.display = 'flex';
  let ch = '<span class="lbl">Ciclos</span>';
  arq.forEach((a, i) => {
   a = a || {};
   const res = a.resultado === 'aprovado' ? 'apr' : (a.resultado === 'devolvido' ? 'dev' : '');
   const rot = a.resultado === 'aprovado' ? 'aprovada' : (a.resultado === 'devolvido' ? 'devolvida' : '—');
   // o contado, nunca o declarado; o arquivado é decisão, e conta pela regra dela
   const cc = contagem(forma(Object.assign({}, a, { fase: 'aprovado' })));
   // resultado arquivado contra a contagem: a cor de pendência, nunca a do resultado
   const cor = res && (cc.d >= cc.a ? 'dev' : 'apr') !== res ? 'pend' : res;
   ch += '<button class="cic ' + cor + (cicloVendo === i ? ' on' : '') + '" onclick="mostrarCiclo(' + i + ')">' +
      'Ciclo ' + esc(a.ciclo == null ? '?' : a.ciclo) +
      '<span class="r">' + rot + (cc.a + cc.d ? ' ' + cc.a + '×' + cc.d : '') + '</span></button>';
  });
  ch += '<button class="cic' + (cicloVendo === null ? ' on' : '') + '" onclick="mostrarCiclo(null)">' +
     'Ciclo ' + esc((estado && estado.ciclo) || '—') + '<span class="r">atual</span></button>';
  faixa.innerHTML = ch;
 } else { faixa.style.display = 'none'; faixa.innerHTML = ''; }
 const hist = (base() || {}).historico || {};
 // Decisão que ainda não vale: nem verde nem vermelha (na revisão, a do retrato revisto)
 const pend = fim ? pendencia(e) : '';
 document.getElementById('steps').innerHTML = PASSOS.map((p,i) => {
  const key = i === 4 ? 'fim' : p[0];
  const temSnap = !!hist[key];
  let cls = 'step' + (i < idx ? ' done' : i === idx ? ' on' : '') + (temSnap ? ' click' : '') + (revendo === key ? ' rev' : '');
  let rot = p[1];
  if (i === 4 && fim) { cls += pend ? '' : e.fase === 'aprovado' ? ' fim-ok' : ' fim-no'; rot = e.fase === 'aprovado' ? 'Aprovada' : 'Devolvida'; }
  const attrs = temSnap ? ' onclick="mostrarFase(\'' + key + '\')" title="Rever o que ocorreu nesta fase"' : '';
  return '<div class="' + cls + '"' + attrs + '>' + rot + '</div>';
 }).join('');
 const rb = document.getElementById('revbar');
 if (revendo) {
  const lbl = (PASSOS.find(p => p[0] === revendo) || [null, revendo])[1];
  rb.style.display = 'flex';
  rb.innerHTML = '⏱ Revendo a fase: <b>' + esc(lbl) + '</b> <button onclick="voltarAoVivo()">▶ voltar ao vivo</button>';
 } else { rb.style.display = 'none'; rb.innerHTML = ''; }
 /* faixa: o resultado da TURMA, ou o que falta para ele valer; quem libera a peça é o gate */
 const ban = document.getElementById('banner');
 if (fim) {
  ban.style.display = 'block';
  ban.className = 'banner ' + (pend ? 'pend' : e.fase === 'aprovado' ? 'ok' : 'dev');
  ban.textContent = pend || (e.fase === 'aprovado' ? 'Aprovada pela turma, por maioria' : 'Devolvida pela turma, por maioria');
 } else ban.style.display = 'none';
 // cartões
 const m = {}; (e.cadeiras || []).forEach(c => { if (typeof c.id === 'string') m[c.id] = c; });
 let html = '';
 CAD.forEach(cd => {
  const st = m[cd.id] || {};
  const pensando = st.status === 'analisando' || st.status === 'debatendo';
  html += '<div class="card" style="border-top-color:' + cd.cor + '"><h3>' + cd.nome + '</h3>' +
   '<div class="st">' + esc(revisou(st) ? 'revisou o voto' : st.status || '—') + (pensando ? ' <span class="think"><i></i><i></i><i></i></span>' : '') + '</div>' +
   chipVoto(st.voto) + '<div class="arg">' + esc(st.argumento || '') + '</div></div>';
 });
 const r = e.relator || {};
 const rv = revisou(r) ? ' · revisou o voto' : '', venc = (r.vencido ? ' · relator vencido' : '') + rv;
 /* Antes da proclamação, o voto do relator aparece no cartão assim que é registrado, com o
   placar parcial ao lado; na decisão, o placar da turma. Os dois CONTADOS, nunca o declarado.
   O relator despachado ('apreciando') está «em análise» enquanto a turma vota, «apurando os
   votos» na apreciação. */
 const ct = contagem(e);
 const parcial = (ct.a + ct.d) ? '<span class="parc">placar parcial · ' + ct.a + '×' + ct.d + '</span>' : '';
 const placar = ' · ' + ct.a + '×' + ct.d;
 const apreciando = e.fase === 'apreciacao' ? 'apurando os votos' : 'em análise';
 const dec = fim ? (pend ? '<span class="voto pend">' + esc(pend.split(':')[0]) + placar + '</span>'
   : '<span class="voto ' + (e.fase === 'aprovado' ? 'aprovar' : 'devolver') + '">' +
    (e.fase === 'aprovado' ? 'Aprovada por maioria' : 'Devolvida por maioria') + placar + venc + '</span>')
  : r.voto ? '<span class="voto ' + classeVoto(r.voto) + '">voto do relator: ' + rotVoto(r.voto) + rv + '</span>' + parcial
  : '<span class="voto pend">' + (r.status === 'apreciando' ? apreciando : 'preside e vota') + '</span>' + parcial;
 html += '<div class="card relator"><h3>Relator — preside e lavra o acórdão</h3>' + dec +
     '<div class="arg">' + esc(r.fundamento || 'O colegiado decide por maioria; o relator preside, profere o primeiro voto e lavra o acórdão (podendo ficar vencido).') + '</div></div>';
 /* Ampliação do art. 942: os dois assentos têm cartão desde a convocação («em análise») ou o
   acionamento; o assento vazio diz "aguardando voto" (é o que falta na turma ampliada). */
 const art = e.art942 || {};
 const assentos = assentos942(art);
 if (art.acionado || assentos.length) {
  html += '<div class="sub942">Ampliação do colegiado — art. 942 do CPC</div>';
  [0, 1].forEach(i => {
   const s = assentos[i] || { v: {}, st: 'aguardando' };
   const v = s.v, analise = s.st === 'em análise' || s.st === 'em debate';
   html += '<div class="card c942"><h3>Des. convocado — Art. 942 (' + (i + 1) + ')' +
    (v.assento ? ' <small>' + esc(v.assento) + '</small>' : '') + '</h3>' +
    '<div class="st">' + esc(s.st) + (analise ? ' <span class="think"><i></i><i></i><i></i></span>' : '') + '</div>' +
    chipVoto(s.st === 'votou' ? v.voto : null) + '<div class="arg">' + esc(v.fundamentacao || '') + '</div></div>';
  });
 }
 document.getElementById('cards').innerHTML = html;
 /* A hora da ata sai do `em` (ISO com fuso) no fuso de quem olha; sem ele, do `hora` gravado. */
 document.getElementById('ata').innerHTML = (e.eventos || []).filter(ev => ev && typeof ev === 'object').reverse().map(ev =>
  '<div class="ev"><span class="h">' + esc(hora(ev.em) || ev.hora) + '</span>' +
  '<span class="q ' + classeQuem(ev.quem) + '">' + esc(ev.quem) + '</span> — ' + esc(semNome(ev.quem, ev.texto)) + '</div>'
 ).join('') || '<div class="ev">Nenhum evento registrado ainda.</div>';
 /* Rótulo do que está na tela: conexão viva (só no Cowork), instantâneo (de quando é, e se a
   sessão anda ou decidiu) ou revisão de fase (NÃO é o estado atual). */
 const meta = document.getElementById('meta');
 if (revendo) {
  const lbl = (PASSOS.find(p => p[0] === revendo) || [null, revendo])[1];
  meta.textContent = 'revendo ' + lbl + ' — não é o estado atual';
 } else if (online && cicloVendo === null) meta.textContent = 'ao vivo';
 else if (semDados) meta.textContent = 'sem sessão registrada';
 else meta.textContent = rotuloInstante(e);
 document.getElementById('pulse').className = 'pulse' + (online && !revendo && cicloVendo === null ? '' : ' off');
 desenha();
 } catch (err) {
  document.getElementById('meta').textContent = 'estado ilegível';
  document.getElementById('pulse').className = 'pulse off';
 }
}
// Auto-refresh AO VIVO: só existe no Cowork (bridge window.cowork), e roda também com o estado
// embutido que traz o caminho (STATE_PATH): o instantâneo aparece na hora e o poll o substitui
// por ESSE arquivo. Sem estado nenhum, procura o mais novo em /sessions. Sem o bridge, poll()
// NUNCA lança nem fica "conectando…" pra sempre: cai no último salvo.
const TEM_COWORK = typeof window !== 'undefined' && !!window.cowork && typeof window.cowork.callMcpTool === 'function';
async function poll() {
 if (!TEM_COWORK) { online = false; render(); return; }
 try {
  const r = await window.cowork.callMcpTool('mcp__workspace__bash', { command: POLL_EXATO || POLL, timeout_ms: 20000 });
  let txt = (r && r.content || []).map(c => c.text || '').join('').trim();
  if (r && r.isError) throw new Error(txt);
  // "ao vivo" só com estado LIDO agora: arquivo ausente deixa o último instantâneo, sem pulso
  online = false;
  if (txt && txt !== 'NOFILE') {
   estado = normaliza(JSON.parse(txt.slice(txt.indexOf('{'))));
   if (!revendo) vista = base();
   online = true;
   try { localStorage.setItem('conselho_ultimo', JSON.stringify(estado)); } catch (e3) {}
  }
 } catch (err) {
  online = false;
  if (!estado) { try { const s = localStorage.getItem('conselho_ultimo'); if (s) { estado = normaliza(JSON.parse(s)); if (!revendo) vista = base(); } } catch (e2) {} }
 }
 render();
}
setInterval(() => { tick++; desenha(); }, 420);
// a escala sai da largura em CSS: mudou a janela, o canvas precisa ser reconstruido
if (typeof window !== 'undefined' && window.addEventListener) {
 let _t = null;
 window.addEventListener('resize', () => { clearTimeout(_t); _t = setTimeout(desenha, 120); });
}
// BOOT (inline) → renderiza o estado injetado na hora; sem estado, o estado-vazio HONESTO.
// Rodapé: "ao vivo" só onde o auto-refresh roda (bridge do Cowork); fora dele fica o do HTML,
// retrato do último estado registrado (regimento §3). Com estado embutido, só pelo caminho EXATO
// (a busca traria o caso mais novo da VM, que pode ser outro), e nunca no painel publicado: o
// poll trocava o pseudonimizado pelo estado cru do caso (medido).
const AUTO_REFRESH = TEM_COWORK && (!BOOT || !!STATE_PATH) && !(BOOT && BOOT.publicado_pseudonimizado);
if (AUTO_REFRESH) {
 document.getElementById('foot').textContent = 'Acompanhamento ao vivo: durante a sessão de julgamento, a turma publica cada evento (argumento, voto, proclamação, decisão) e este plenário se atualiza a cada 5 segundos. Fora de sessão, permanece o último estado registrado. A aprovação da turma (por maioria) atesta o cumprimento do padrão do escritório — o relator preside, vota e pode ficar vencido. A decisão de protocolar é sempre do advogado.';
}
if (BOOT) { render(); }
if (AUTO_REFRESH) { setInterval(poll, 5000); poll(); }
else if (!BOOT) { render(); }
