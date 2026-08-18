#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Monta o index.html do Gatinho — une a tela inicial e a tela de conversa.

Entradas (do Pai):
  Qwen_html_20260817_nrlx4qhaw.html  -> tela INICIAL
  Qwen_html_20260817_95ntu0rzb.html  -> tela de CONVERSA
  ChatGPT Image 17_08_2026...png     -> o gato novo

O que muda em relacao aos originais:
  * o <img> apontava para chatgpt.com/backend-api/... — link assinado que EXPIRA.
    Agora a arte mora no projeto (assets/gatinho.png) e vai embutida em base64,
    entao o arquivo abre em qualquer lugar, offline, para sempre.
  * a arte foi tratada: fundo preto virou transparente (o painel e #0a0906, nao
    #000 — colada crua aparecia um quadrado), alpha binario e uma cor so.
    863 KB -> 4,5 KB.
"""
from __future__ import annotations

import base64
from pathlib import Path

AQUI = Path(__file__).parent
GATO = AQUI / "assets" / "gatinho.png"
SAIDA = AQUI / "index.html"


def b64(p: Path) -> str:
    return base64.b64encode(p.read_bytes()).decode()


CSS = """
:root{color-scheme:dark;
 --bg:#0a0906;--panel:#0d0c09;--amber:#f0a924;--amber-dim:#8a6a20;
 --txt:#d8d0c0;--whit:#e8e0d0;--gray:#9a938a;--blue:#58a6ff;
 --green:#3fb950;--red:#f85149;--orange:#f0883e;--yellow:#f0c040;--line:#3a352c}
*{margin:0;padding:0;box-sizing:border-box;scrollbar-width:thin;scrollbar-color:#3a352c #0d0c09}
::-webkit-scrollbar{width:10px;height:10px;background:#0d0c09}
::-webkit-scrollbar-thumb{background:#3a352c;border:2px solid #0d0c09;border-radius:5px}
body{background:#000;min-height:100vh;display:flex;align-items:center;justify-content:center;
 font-family:ui-monospace,'Cascadia Mono','JetBrains Mono',Consolas,monospace;
 font-size:14px;color:var(--txt);padding:18px}
body::after{content:"";position:fixed;inset:0;pointer-events:none;
 background:repeating-linear-gradient(0deg,transparent 0 3px,rgba(0,0,0,.22) 3px 6px)}
.cli{width:1240px;max-width:100%;background:var(--bg);border:1px solid var(--amber);
 padding:22px 26px;box-shadow:0 0 30px rgba(240,169,36,.08);
 display:flex;flex-direction:column}
.cli.chat-on{min-height:88vh}
.box{border:1px solid var(--amber);background:var(--panel);padding:12px 16px}
.c-plan{color:var(--amber)} .c-full{color:var(--red)} .c-perm{color:var(--green)}
.hidden{display:none!important}

/* ================= tela inicial ================= */
.hero{display:flex;gap:30px;align-items:flex-start;position:relative}
#catImg{width:250px;image-rendering:pixelated;cursor:pointer;
 filter:drop-shadow(0 0 10px rgba(240,169,36,.28))}
pre#cat{color:var(--amber);font-size:10px;line-height:1.05;cursor:pointer}
.cat-cap{color:var(--amber-dim);font-size:11px;margin-top:6px}
.chips{position:absolute;top:0;right:0;display:flex;gap:8px}
.chip{background:none;border:1px solid var(--amber-dim);color:var(--amber);font:inherit;
 font-size:11px;padding:2px 8px;cursor:pointer}
.chip:hover{border-color:var(--amber);background:rgba(240,169,36,.1)}
pre#title{color:var(--amber);font-size:9px;line-height:1.05;margin-bottom:8px;
 text-shadow:0 0 8px rgba(240,169,36,.5)}
.sub{color:var(--amber);margin-bottom:16px}
.modebox{display:grid;grid-template-columns:110px 1fr;row-gap:6px;width:620px;max-width:100%}
.modebox .k,.modebox .v{color:var(--whit)}
.tabs{display:flex;gap:6px;margin:22px 0 0}
.tab{background:none;border:1px solid #4a443a;font:inherit;padding:6px 20px;cursor:pointer;
 position:relative;top:1px}
#tab-plan{color:var(--amber)} #tab-full{color:var(--red)} #tab-perm{color:var(--green)}
.tab.active#tab-plan{border-color:var(--amber);background:var(--bg)}
.tab.active#tab-full{border-color:var(--red);background:var(--bg)}
.tab.active#tab-perm{border-color:var(--green);background:var(--bg)}
.main{display:grid;grid-template-columns:1fr 340px;gap:16px;margin-top:-1px}
#log{max-height:330px;min-height:200px;overflow-y:auto;padding-right:6px}
.line{display:grid;grid-template-columns:92px 64px 1fr;gap:10px;margin:4px 0;white-space:pre-wrap}
.t{color:var(--gray)}
.INFO{color:var(--blue)} .PLAN{color:var(--amber)} .READ{color:var(--orange)}
.THINK{color:var(--orange);font-style:italic} .EDIT{color:var(--yellow)} .RUN{color:var(--amber)}
.WRITE{color:var(--yellow)} .TEST{color:var(--yellow)} .OK,.DONE{color:var(--green)}
.stats .row{display:grid;grid-template-columns:110px 1fr;gap:8px;margin:5px 0}
.stats .k,.stats .v{color:var(--whit)}
.v.grn{color:var(--green)} .v.am{color:var(--amber)} .v.rd{color:var(--red)}
.stats hr{border:none;border-top:1px solid var(--line);margin:12px 0}

/* ================= tela de conversa ================= */
.convbar{display:flex;align-items:center;gap:14px;border:1px solid var(--amber);
 padding:8px 14px;color:var(--amber);margin-bottom:12px}
.convbar .sp{flex:1}
.convbar img{width:26px;image-rendering:pixelated;vertical-align:middle}
.mbtn{background:none;border:1px solid var(--line);font:inherit;font-size:11px;
 padding:2px 10px;cursor:pointer}
#mb-plan{color:var(--amber)} #mb-full{color:var(--red)} #mb-perm{color:var(--green)}
.mbtn.on#mb-plan{border-color:var(--amber)}
.mbtn.on#mb-full{border-color:var(--red)}
.mbtn.on#mb-perm{border-color:var(--green)}
#chat{flex:1;overflow-y:auto;padding:4px 2px;min-height:340px}
.user{margin:20px 0 14px;max-width:70%;border-top:1px solid var(--line);
 border-bottom:1px solid var(--line);padding:6px 2px}
.user b{color:var(--whit)}
.user::before{content:"• ";color:var(--amber)}
.agent{border:1px solid var(--amber);position:relative;margin:16px 0;padding:12px 14px}
.agent .name{position:absolute;top:-9px;left:10px;background:var(--bg);padding:0 6px;color:var(--amber)}
.agent .content{white-space:pre-wrap}
.msg{color:var(--txt)}
.think{color:var(--gray);font-style:italic;margin:4px 0}
.think::before{content:"• ";color:var(--amber)}
.tool{margin:6px 0}
.tool .b::before{content:"• ";color:var(--amber)}
.t-read{color:var(--blue)} .t-write{color:var(--green)} .t-edit{color:var(--yellow)}
.t-run{color:var(--green)} .t-ok{color:var(--green)} .t-block{color:var(--red)} .t-perm{color:var(--green)}
.out{color:var(--gray);margin:2px 0 2px 18px;white-space:pre}
.out .g{color:var(--green)}
.worked{border-top:1px solid var(--line);margin-top:12px;padding-top:6px;color:var(--gray);font-size:12px}
.codeblock{border:1px solid var(--line);background:#080705;color:#9ad17d;
 margin:6px 0 6px 18px;padding:8px 12px;white-space:pre;overflow-x:auto}
.codeblock .fn{color:var(--amber)}
.diff{white-space:pre;margin:2px 0 2px 18px}
.d-red{color:var(--red)} .d-grn{color:var(--green)} .d-gray{color:var(--gray)}

/* ================= comum: status, input, rodape ================= */
.statusbar{display:flex;justify-content:space-between;gap:16px;align-items:center;
 border:1px solid var(--line);background:var(--panel);margin-top:10px;padding:6px 14px;font-size:13px}
.statusbar .right{display:flex;gap:14px;align-items:center;color:var(--whit)}
.statusbar .dim{color:var(--gray)}
.bar b{color:var(--amber);font-weight:normal} .bar i{color:#333;font-style:normal}
#sbStream{color:var(--red);animation:blink .8s steps(1) infinite}
#sbLive{border:1px solid var(--line);padding:1px 8px;font-size:11px;cursor:help}
#sbLive.real{color:var(--green);border-color:var(--green)}
#sbLive.demo{color:var(--yellow);border-color:var(--yellow)}
#sbPasta{border:1px solid var(--line);padding:1px 8px;font-size:11px;color:var(--gray)}
#sbPasta.c-full{color:var(--red);border-color:var(--red)}
.inputwrap{position:relative;margin-top:14px}
.input{display:flex;align-items:center;gap:10px}
.prompt{color:var(--amber);font-weight:bold}
.input .sep{color:var(--amber-dim)}
.input input{flex:1;background:none;border:none;outline:none;color:var(--whit);font:inherit;
 caret-color:var(--amber)}
.input input::placeholder{color:#5a544a}
.cursor{color:var(--whit);animation:blink 1s steps(1) infinite}
.slash{position:absolute;left:0;right:0;bottom:calc(100% + 6px);border:1px solid var(--amber);
 background:var(--panel);display:none;z-index:9;max-height:340px;overflow-y:auto}
.slash.open{display:block}
.slash .item{padding:6px 14px;cursor:pointer;display:flex;gap:14px}
.slash .item .c{color:var(--amber);min-width:150px}
.slash .item .d{color:var(--gray)}
.slash .item.sel,.slash .item:hover{background:rgba(240,169,36,.14)}
.permb{background:none;border:1px solid var(--amber-dim);color:var(--amber);font:inherit;
 font-size:11px;padding:1px 8px;cursor:pointer;margin-left:4px}
.permb:hover{border-color:var(--amber);background:rgba(240,169,36,.12)}
.slash .head{padding:4px 14px;color:var(--amber-dim);font-size:11px;border-bottom:1px solid var(--line)}
/* 58 comandos numa lista corrida viram parede; a categoria da o mapa */
.slash .cat{padding:6px 14px 2px;color:var(--amber-dim);font-size:10px;letter-spacing:.12em;
 text-transform:uppercase;opacity:.75}
footer{display:flex;justify-content:space-between;gap:14px;border:1px solid var(--amber);
 margin-top:14px;padding:8px 14px;color:var(--amber)}
footer .dim{color:var(--amber-dim)}
@keyframes blink{50%{opacity:0}}
@media(max-width:900px){
 .hero{flex-direction:column;gap:16px} .chips{position:static;margin-top:8px}
 .main{grid-template-columns:1fr} #catImg{width:180px} .modebox{width:100%}
}
"""

CORPO = """
<div class="cli">

  <!-- ========== TELA INICIAL ========== -->
  <div id="viewHome">
    <header class="hero">
      <div id="catWrap">
        <img id="catImg" alt="Gatinho — mascote em pixel art" src="__GATO__">
        <pre id="cat" class="hidden"></pre>
        <div class="cat-cap">avatar: <span id="catName">imagem</span> · [V] varia · [C] oculta</div>
      </div>
      <div class="chips">
        <button class="chip" id="btnVar">🐱 variar [V]</button>
        <button class="chip" id="btnCat">👁 gato [C]</button>
        <button class="chip" id="btnStats">📊 stats [S]</button>
      </div>
      <div>
        <pre id="title"></pre>
        <p class="sub">assistente de código. focado. rápido. curioso.</p>
        <div class="modebox box">
          <span class="k">Tipo:</span><span class="v c-plan">agente de código</span>
          <span class="k">Modo:</span><span class="v" id="mName"></span>
          <span class="k">Permissões:</span><span class="v" id="mPerm"></span>
          <span class="k">Descrição:</span><span class="v" id="mDesc"></span>
        </div>
      </div>
    </header>

    <nav class="tabs">
      <button class="tab" id="tab-plan">PLANEJAMENTO</button>
      <button class="tab" id="tab-full">FULL ACESSO ●</button>
      <button class="tab" id="tab-perm">PEDIR PERMISSÃO</button>
    </nav>

    <section class="main">
      <div class="box"><div id="log"></div></div>
      <aside class="box stats" id="stats"></aside>
    </section>
  </div>

  <!-- ========== TELA DE CONVERSA ========== -->
  <div id="viewChat" class="hidden" style="display:flex;flex-direction:column;flex:1">
    <div class="convbar">
      <img src="__GATO_MINI__" alt=""><span>GATINHO CLI</span><span class="sp"></span>
      <button class="mbtn" id="mb-plan">PLAN</button>
      <button class="mbtn on" id="mb-full">FULL</button>
      <button class="mbtn" id="mb-perm">PERM</button>
      <button class="mbtn" id="btnParar" title="interrompe a tarefa">■ parar</button>
      <button class="mbtn" id="btnHome">◀ início</button>
    </div>
    <div id="chat"></div>
  </div>

  <!-- ========== COMUM ========== -->
  <div class="statusbar">
    <span id="sbMode">modo: —</span>
    <span id="sbLive" title="clique para saber">verificando…</span>
    <span id="sbPasta" class="chipst" title=""></span>
    <span id="sbStream"></span>
    <span class="right">
      <span id="sbTime">⏱ 0.0s</span>
      <span id="sbTok">tokens 0/16K</span>
      <span class="bar"><b id="tokB"></b><i id="tokI"></i></span>
      <span class="dim">modelo: deltacoder-9b</span>
    </span>
  </div>

  <div class="inputwrap">
    <div class="slash" id="slash"></div>
    <div class="box input">
      <span class="prompt">gatinho&gt;</span><span class="sep">|</span>
      <input id="cmd" placeholder="Digite qualquer coisa e veja a IA agir... ou / para comandos"
             autocomplete="off">
      <span class="cursor">▮</span>
    </div>
  </div>

  <footer>
    <span><span class="dim">[Dica]</span> / comandos&nbsp; | &nbsp;Ctrl+L limpar&nbsp; |
      &nbsp;/modo plan·full·perm&nbsp; | &nbsp;no PLANO responda <b>sim</b> p/ implementar</span>
    <span>v0.1.0</span>
  </footer>
</div>
"""

JS = r"""
const $=s=>document.querySelector(s),sleep=ms=>new Promise(r=>setTimeout(r,ms)),
      now=()=>new Date().toTimeString().slice(0,8);

/* ===== titulo em blocos ===== */
const F={G:[" ███ ","█   █","█    ","█ ███","█   █","█   █"," ███ "],
A:[" ███ ","█   █","█   █","█████","█   █","█   █","█   █"],
T:["█████","  █  ","  █  ","  █  ","  █  ","  █  ","  █  "],
I:["███"," █ "," █ "," █ "," █ "," █ ","███"],
N:["█   █","██  █","███ █","█ ███","█  ██","█   █","█   █"],
H:["█   █","█   █","█   █","█████","█   █","█   █","█   █"],
O:[" ███ ","█   █","█   █","█   █","█   █","█   █"," ███ "],
C:[" ████","█    ","█    ","█    ","█    ","█    "," ████"],
L:["█    ","█    ","█    ","█    ","█    ","█    ","█████"]," ":["  ","  ","  ","  ","  ","  ","  "]};
let tr=[0,1,2,3,4,5,6].map(()=>"");
for(const ch of "GATINHO CLI")for(let i=0;i<7;i++)tr[i]+=F[ch][i]+" ";
$("#title").textContent=tr.join("\n");

/* ===== avatar: imagem do projeto + variantes ASCII ===== */
const CATS=[{n:"blocos █",a:`
            ██              ██
           ██ █            █ ██
           ██ ██████████████ ██
          ██████████████████████
          ████  █  █████  █  ███
       ██ ████ █ █ █████ █ █ ███ ██
          ████  █  █████  █  ███
       ██ ████     █████     ███ ██
          ██████████   █████████
          ███████████ ██████████
          ███████   ███   ████████
            ██████████████████
     ███      ████████████████
    █████    ██████████████████
   ██  ██   ████████████████████
  ███     ██████████████████████
  ███     ██████ ███ ████ ████`},
{n:"mini",a:`
 ██      ██
 █▓█    █▓█
 ██████████
 █ ▀█  ▀█ █
 █▓▓▄▄▓▓▓▓█
 ▐█▓▓▓▓▓▓█▌
  ▀█▓▓▓▓█▀
   ▀▀  ▀▀`}];
let ci=-1;
function drawCat(){
 if(ci===-1){$("#catImg").classList.remove("hidden");$("#cat").classList.add("hidden");
  $("#catName").textContent="imagem"}
 else{$("#catImg").classList.add("hidden");$("#cat").classList.remove("hidden");
  $("#cat").textContent=CATS[ci].a;$("#catName").textContent=CATS[ci].n}}
function cycleCat(){ci=ci===-1?0:(ci+1>=CATS.length?-1:ci+1);drawCat()}
$("#catImg").onerror=()=>{ci=0;drawCat()};
$("#catImg").onclick=cycleCat;$("#cat").onclick=cycleCat;$("#btnVar").onclick=cycleCat;
$("#btnCat").onclick=()=>$("#catWrap").classList.toggle("hidden");
$("#btnStats").onclick=()=>$("#stats").classList.toggle("hidden");

/* ===== as duas telas ===== */
let emChat=false;
function irParaChat(){if(emChat)return;emChat=true;
 document.querySelector(".cli").classList.add("chat-on");
 $("#viewHome").classList.add("hidden");$("#viewChat").classList.remove("hidden")}
function irParaHome(){emChat=false;
 document.querySelector(".cli").classList.remove("chat-on");
 $("#viewChat").classList.add("hidden");$("#viewHome").classList.remove("hidden")}
$("#btnHome").onclick=()=>{if(!busy)irParaHome()};
$("#btnParar").onclick=async()=>{if(!AOVIVO)return;
 try{await fetch("/api/parar",{method:"POST"});cardAtual();
  inAgent(`<div class="think">parando…</div>`)}catch(e){}};

/* ===== modos (as duas telas apontam para o mesmo estado) ===== */
const MODES={
plan:{name:"PLANEJAMENTO",cls:"c-plan",perm:"somente leitura + proposta de plano",
 desc:"Converse montando o plano. No final o modelo pergunta se está bom; respondendo sim, ele implementa em FULL ACESSO."},
full:{name:"FULL ACESSO",cls:"c-full",perm:"leitura + escrita + execução (sem confirmação)",
 desc:"Agente age sozinho: pensa, chama tools, cria/edita arquivos e roda testes."},
perm:{name:"PEDIR PERMISSÃO",cls:"c-perm",perm:"cada ação precisa de y/n",
 desc:"O agente propõe cada tool call e espera sua aprovação (y) ou negação (n)."}};
let mode="full",busy=false,awaitingPerm=null,awaitingPlan=false,TX=null,permPendente=null;
function tx(k,padrao){return (TX&&TX[k])||padrao}
function setMode(m){mode=m;awaitingPlan=false;
 for(const k of["plan","full","perm"]){
  $("#tab-"+k).classList.toggle("active",k===m);
  $("#mb-"+k).classList.toggle("on",k===m)}
 $("#mName").textContent=MODES[m].name;$("#mName").className="v "+MODES[m].cls;
 $("#mPerm").textContent=MODES[m].perm;$("#mDesc").textContent=MODES[m].desc;
 $("#sbMode").textContent=tx("status.mode","modo")+": "+tx("mode."+m,MODES[m].name);
 $("#sbMode").className=MODES[m].cls;
 renderStats(m)}
async function trocarPolitica(k){
 if(busy)return;setMode(k);
 if(AOVIVO){try{await fetch("/api/comando",{method:"POST",
   headers:{"Content-Type":"application/json"},body:JSON.stringify({texto:"/mode "+k})})}
  catch(e){}}}
["plan","full","perm"].forEach(k=>{
 $("#tab-"+k).onclick=()=>trocarPolitica(k);
 $("#mb-"+k).onclick=()=>trocarPolitica(k)});

/* ===== tokens + timer ===== */
let tokens=2100,respStart=0,timerInt=null,tokStart=0;const MAXT=16000;
function updateBar(){$("#sbTok").textContent=`${tx("label.tokens","tokens")} ${(tokens/1000).toFixed(1)}K/16K`;
 const f=Math.round(tokens/MAXT*20);
 $("#tokB").textContent="█".repeat(f);$("#tokI").textContent="█".repeat(20-f)}
function startResp(){tokStart=tokens;respStart=performance.now();$("#sbStream").textContent="● gerando…";
 timerInt=setInterval(()=>$("#sbTime").textContent="⏱ "+((performance.now()-respStart)/1000).toFixed(1)+"s",100)}
function endResp(){clearInterval(timerInt);$("#sbStream").textContent="";
 return{t:((performance.now()-respStart)/1000).toFixed(2),d:tokens-tokStart}}

/* ===== log da tela inicial ===== */
function add(tag,cls,msg){const d=document.createElement("div");d.className="line";
 d.innerHTML=`<span class="t">[${now()}]</span><span class="${cls}"></span><span></span>`;
 d.children[1].textContent=tag;d.children[2].textContent=msg;
 $("#log").appendChild(d);$("#log").scrollTop=$("#log").scrollHeight}

/* ===== chat ===== */
const chat=()=>$("#chat");
const scroll=()=>{chat().scrollTop=chat().scrollHeight};
function userMsg(v){const d=document.createElement("div");d.className="user";
 d.innerHTML="<b></b>";d.querySelector("b").textContent=v;chat().appendChild(d);scroll()}
let box=null,content=null,cardAberto=false;
function newAgent(){box=document.createElement("div");box.className="agent";
 box.innerHTML=`<span class="name">Gatinho</span><div class="content"></div>`;
 chat().appendChild(box);content=box.querySelector(".content");cardAberto=true;scroll()}
/* reaproveita o card em aberto: pensar e responder sao a MESMA fala do agente */
function cardAtual(){if(!cardAberto||!content)newAgent();return content}
function inAgent(html){const d=document.createElement("div");d.innerHTML=html;
 content.appendChild(d);scroll();return d}
function think(m){cardAtual();inAgent(`<div class="think">pensando: ${m} …</div>`);
 tokens+=24;updateBar()}
function tool(cls,tag,txt){inAgent(`<div class="tool"><span class="b ${cls}">${tag}</span> <span>${txt}</span></div>`)}
function out(html){inAgent(`<div class="out">${html}</div>`)}
function codeBlock(p,c){const d=document.createElement("div");d.className="codeblock";
 d.innerHTML=`<span class="fn">📄 ${p}</span>\n`;d.appendChild(document.createTextNode(c));
 content.appendChild(d);scroll()}
async function streamModel(text){cardAtual();startResp();
 const d=document.createElement("div");d.className="msg";content.appendChild(d);
 for(const w of text.split(" ")){d.textContent+=w+" ";tokens+=1+Math.floor(w.length/4);
  updateBar();scroll();await sleep(38)}
 const r=endResp();inAgent(`<div class="worked">─ Worked for ${r.t}s · +${r.d} tokens ─</div>`);
 cardAberto=false}                       /* fecha: a proxima fala abre card novo */

/* ===== ligacao com o motor real (servidor) ===== */
const AOVIVO = location.protocol.startsWith("http");
let estadoSrv = null;

async function verificarServidor(){
 const el=$("#sbLive");
 if(!AOVIVO){el.textContent="DEMO (sem servidor)";el.className="demo";
  el.title="Aberto como arquivo. Para valer de verdade rode ./gatinho.sh";return}
 try{
  const r=await fetch("/api/estado");estadoSrv=await r.json();
  el.textContent="AO VIVO";el.className="real";
  el.title=`modelo ${estadoSrv.modelo} · projeto ${estadoSrv.projeto}`;
  aplicarEstado(estadoSrv);
 }catch(e){el.textContent="servidor fora do ar";el.className="demo"}}

function aplicarTextos(tx){
 if(!tx)return;
 const ph=document.querySelector("#cmd");if(tx["input.placeholder"])ph.placeholder=tx["input.placeholder"];
 const sub=document.querySelector(".sub");if(tx["app.sub"])sub.textContent=tx["app.sub"];
 for(const [k,el] of [["mode.plan","#tab-plan"],["mode.full","#tab-full"],["mode.perm","#tab-perm"]])
  if(tx[k])document.querySelector(el).textContent=tx[k]+(el==="#tab-full"?" ●":"");
 for(const [k,el] of [["mode.plan","#mb-plan"],["mode.full","#mb-full"],["mode.perm","#mb-perm"]])
  if(tx[k])document.querySelector(el).textContent=tx[k].split(" ")[0];
 const ks=document.querySelectorAll(".modebox .k");
 const rot=[tx["label.type"],tx["label.mode"],tx["label.perms"],tx["label.desc"]];
 ks.forEach((el,i)=>{if(rot[i])el.textContent=rot[i]});
 const tipo=document.querySelector(".modebox .v.c-plan");
 if(tipo&&tx["label.agent"])tipo.textContent=tx["label.agent"];
 if(tx["live.on"]&&AOVIVO){const l=$("#sbLive");if(l.classList.contains("real"))l.textContent=tx["live.on"]}
 TX=tx;
 $("#sbMode").textContent=(tx["status.mode"]||"modo")+": "+(tx["mode."+mode]||MODES[mode].name);
 const f=document.querySelector("footer span");
 if(f&&tx["hint.commands"])f.innerHTML=`<span class="dim">[${tx["footer.tip"]||"Dica"}]</span> / ${tx["hint.commands"]}&nbsp; | &nbsp;Ctrl+L ${tx["hint.clear"]||"limpar"}&nbsp; | &nbsp;/modo plan·full·perm&nbsp; | &nbsp;${tx["hint.plan"]||""}`;
 updateBar();}

function aplicarEstado(e){
 if(!e)return;
 if(e.textos)aplicarTextos(e.textos);
 if(e.pasta){const el=$("#sbPasta");if(el){el.textContent=(e.sandbox?"🧪 ":"⚠ ")+e.pasta.split("/").slice(-2).join("/");
  el.className="chipst "+(e.sandbox?"":"c-full");el.title=e.aviso_sandbox||""}}
 if(e.tokens!=null){tokens=e.tokens;updateBar()}
 if(e.modo&&MODES[e.modo]&&e.modo!==mode)setMode(e.modo);
 const dim=document.querySelector(".statusbar .dim");
 if(dim&&e.modelo)dim.textContent="modelo: "+e.modelo;}

/* le o SSE do POST /api/chat */
async function enviarReal(texto){
 irParaChat();userMsg(texto);busy=true;
 let cardStream=null,alvo=null;
 try{
  const r=await fetch("/api/chat",{method:"POST",
    headers:{"Content-Type":"application/json"},body:JSON.stringify({texto})});
  if(!r.ok||!r.body)throw new Error("HTTP "+r.status);
  const leitor=r.body.getReader(),dec=new TextDecoder();let buf="";
  startResp();
  for(;;){
   const {value,done}=await leitor.read();if(done)break;
   buf+=dec.decode(value,{stream:true});
   const partes=buf.split("\n\n");buf=partes.pop();
   for(const bloco of partes){
    const linha=bloco.split("\n").find(l=>l.startsWith("data:"));if(!linha)continue;
    let ev;try{ev=JSON.parse(linha.slice(5))}catch(e){continue}
    if(ev.tipo==="ping"){/* so mantem a conexao viva */}
    else if(ev.tipo==="modo"){/* a barra ja mostra; o modo real vem do servidor */}
    else if(ev.tipo==="plano"){cardAtual();
     inAgent(`<div class="think">plano: ~${ev.estimativa} tokens · harness ${ev.harness} — ${ev.motivo}</div>`)}
    else if(ev.tipo==="acao"){cardAtual();tool(ev.classe,ev.tag,ev.texto)}
    else if(ev.tipo==="resultado"){
     if(ev.erro)out(`<span style="color:var(--red)">${escapar(ev.texto.split("\n")[0])}</span>`);
     else if(ev.ferramenta==="bash")out(escapar(ev.texto).slice(0,900));
    }
    else if(ev.tipo==="texto"){
     if(!cardStream){cardAtual();alvo=document.createElement("div");alvo.className="msg";
      content.appendChild(alvo);cardStream=true}
     alvo.textContent+=ev.texto;scroll()}
    else if(ev.tipo==="aviso"){cardAtual();
     inAgent(`<div class="think">${escapar(ev.texto)}</div>`)}
    else if(ev.tipo==="metricas"){if(ev.tokens){tokens=ev.tokens;updateBar()}}
    else if(ev.tipo==="permissao"){cardAtual();
     const d=document.createElement("div");d.className="tool";
     d.innerHTML=`<span class="b t-perm">🔒 ${escapar(ev.ferramenta)}</span> <span>${escapar(ev.alvo)}</span> `+
      `<button class="permb sim">✔ permitir</button> <button class="permb nao">✖ negar</button>`;
     content.appendChild(d);scroll();
     const decidir=async ok=>{d.querySelectorAll(".permb").forEach(b=>b.remove());
      d.insertAdjacentHTML("beforeend",`<span class="${ok?"t-ok":"t-block"}"> → ${ok?"permitido":"negado"}</span>`);
      await fetch("/api/permissao",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({ok})})};
     d.querySelector(".sim").onclick=()=>decidir(true);
     d.querySelector(".nao").onclick=()=>decidir(false);
     permPendente=decidir}
    else if(ev.tipo==="politica"){setMode(ev.modo)}
    else if(ev.tipo==="fase"){$("#sbFase")&&($("#sbFase").textContent=ev.fase==="plan"?"⌕":"▶")}
    else if(ev.tipo==="idioma"){aplicarTextos(ev.textos);
     cardAtual();inAgent(`<div class="think">idioma detectado: ${ev.idioma} (${ev.confianca})</div>`)}
    else if(ev.tipo==="sandbox"){cardAtual();
     inAgent(`<div class="think">${escapar(ev.aviso)} → ${escapar(ev.pasta)}</div>`)}
    else if(ev.tipo==="erro"){cardAtual();
     inAgent(`<div class="tool"><span class="b t-block">✗ erro</span> <span>${escapar(ev.texto)}</span></div>`)}
    else if(ev.tipo==="fim"){
     if(!cardStream&&ev.texto){cardAtual();const d=document.createElement("div");
      d.className="msg";d.textContent=ev.texto;content.appendChild(d)}
     const m=ev.metricas||{};const r2=endResp();
     inAgent(`<div class="worked">─ ${r2.t}s · tools ${m.executadas||0} executadas / ${m.emitidas||0} emitidas`+
             `${m.bloqueadas?" / "+m.bloqueadas+" bloqueadas":""} · ${m.turnos||0} turnos ─</div>`);
     cardAberto=false;aplicarEstado(ev.estado)}
   }
  }
 }catch(e){cardAtual();
  inAgent(`<div class="tool"><span class="b t-block">✗ erro</span> <span>${escapar(String(e))} — o servidor caiu ou o modelo nao respondeu</span></div>`);
  endResp()}
 finally{busy=false}}

function escapar(t){const d=document.createElement("div");d.textContent=t==null?"":String(t);
 return d.innerHTML}

/* ===== demo (so quando aberto como arquivo, sem servidor) ===== */
async function implementDemo(ctx){
 think("analisando: "+ctx);await sleep(700);
 await streamModel("[DEMO] Sem servidor eu nao chamo modelo nenhum — isto e roteiro fixo. Rode ./gatinho.sh para valer.");
 tool("t-read","Read","src/cache/memory.ts");await sleep(400);tokens+=40;updateBar();
 tool("t-write","Wrote","src/cache/memory.ts (12 linhas)");
 codeBlock("src/cache/memory.ts",`export class LRUCache<K,V> {\n  private map = new Map<K,V>();\n  get(k: K){ return this.map.get(k) }\n}`);
 tokens+=96;updateBar();await sleep(300);
 tool("t-run","Ran","pnpm test --filter cache");
 out(`✓ <span class="g">26/26 testes passaram</span>  [100%] (fingido)`);
 await streamModel("[DEMO] fim do roteiro.")}

async function handleUser(v){
 if(busy)return;
 if(AOVIVO)return enviarReal(v);
 irParaChat();userMsg(v);busy=true;
 try{await implementDemo(v)}finally{busy=false}}

/* ===== input ===== */
$("#cmd").addEventListener("keydown",async e=>{
 if(e.key==="Escape")return closeSlash();
 if($("#slash").classList.contains("open")){
  if(e.key==="ArrowDown"){e.preventDefault();sel=Math.min(sel+1,filtered.length-1);return openSlash()}
  if(e.key==="ArrowUp"){e.preventDefault();sel=Math.max(sel-1,0);return openSlash()}
  if(e.key==="Tab"||e.key==="Enter"){e.preventDefault();return pick(sel)}}
 if(e.key!=="Enter")return;
 const v=e.target.value.trim();if(!v)return;e.target.value="";closeSlash();
 if(permPendente&&(v==="y"||v==="n"||v==="s")){const f=permPendente;permPendente=null;
  f(v!=="n");return}
 if(awaitingPerm&&(v==="y"||v==="n")){const a=awaitingPerm;awaitingPerm=null;
  if(v==="y"){tool("t-ok","✔ perm",a.action+" → aprovado");a.res(true)}
  else{tool("t-block","✖ perm",a.action+" → negado");a.res(false)}return}
 if(v.startsWith("/"))return runCmd(v);
 handleUser(v)});

/* ===== slash ===== */
/* A paleta vem do REGISTRO do motor (GET /api/comandos), nao de lista escrita aqui.
   Ate 2026-08-18 esta constante tinha 8 comandos na mao; tres nao existiam no motor
   (/agents, /limpar, /modo) e 50 reais estavam invisiveis — inclusive /model. Quem
   digitava "/" via um menu que nao correspondia ao programa. */
let CMDS=[["/help","lista todos os comandos","/help","sistema"],
 ["/status","status da run","/status","sistema"],
 ["/tools","ferramentas disponiveis","/tools","ferramentas"],
 ["/config","configuracao do gatinho","/config","sistema"],
 ["/limpar","limpa e volta ao inicio","/limpar","sistema"],
 ["/modo plan|full|perm","troca o modo do agente","/modo <m>","modo"]];
let ALIASES={};
async function carregarComandos(){
 if(!AOVIVO)return;
 try{const r=await fetch("/api/comandos");const d=await r.json();
  if(d.comandos&&d.comandos.length){
   CMDS=d.comandos.map(c=>[c.nome,c.desc,c.uso,c.categoria]);
   ALIASES=d.aliases||{};
   const el=$("#slash-total");if(el)el.textContent=d.total;}
 }catch(e){/* fica a lista minima do modo DEMO */}}
carregarComandos();

let sel=0,filtered=[];
function openSlash(){const v=$("#cmd").value;
 if(!v.startsWith("/")||v.includes(" "))return closeSlash();
 const termo=v.slice(1).toLowerCase();
 /* casa por prefixo, por pedaco do nome e pela descricao — com 58 comandos,
    exigir prefixo exato esconde o comando de quem nao sabe o nome dele */
 const pref=[],meio=[];
 for(const c of CMDS){const nome=c[0].toLowerCase();
  if(nome.startsWith("/"+termo))pref.push(c);
  else if(termo&&(nome.includes(termo)||(c[1]||"").toLowerCase().includes(termo)))meio.push(c);}
 filtered=pref.concat(meio).slice(0,60);sel=0;
 if(!filtered.length){$("#slash").innerHTML=
   `<div class="head">nenhum comando com "${v}" — Esc fecha</div>`;
  $("#slash").classList.add("open");return}
 let cat="",html=`<div class="head">${filtered.length} de <span id="slash-total">${CMDS.length}</span> comandos — ↑↓ navegar · Enter/Tab selecionar · Esc fechar</div>`;
 filtered.forEach((c,i)=>{
  if(c[3]&&c[3]!==cat){cat=c[3];html+=`<div class="cat">${cat}</div>`}
  html+=`<div class="item ${i===sel?"sel":""}" data-i="${i}"><span class="c">${c[0]}</span><span class="d">${c[1]||""}</span></div>`});
 $("#slash").innerHTML=html;$("#slash").classList.add("open");
 $("#slash").querySelectorAll(".item").forEach(el=>el.onclick=()=>pick(+el.dataset.i))}
function closeSlash(){$("#slash").classList.remove("open")}
function pick(i){if(!filtered[i])return closeSlash();
 const c=filtered[i],nome=c[0].split(" ")[0],uso=c[2]||"";closeSlash();
 /* comando que pede argumento nao roda sozinho: deixa digitado com o espaco */
 if(/[<\[]/.test(uso.replace(nome,""))){$("#cmd").value=nome+" ";}
 else{$("#cmd").value="";runCmd(nome)}
 $("#cmd").focus()}
$("#cmd").addEventListener("input",openSlash);

function responder(txt){if(emChat){newAgent();content.textContent=txt;cardAberto=false}
 else add("INFO","INFO",txt)}
function limpar(){chat().innerHTML="";$("#log").innerHTML="";box=content=null;cardAberto=false;irParaHome();
 add("INFO","INFO","Gatinho CLI inicializado com sucesso.");
 add("INFO","INFO","digite qualquer mensagem para ver a simulação streaming 🐾")}
async function runCmd(v){
 if(v==="/limpar"&&!AOVIVO)return limpar();
 if(AOVIVO){
  try{
   const r=await fetch("/api/comando",{method:"POST",
     headers:{"Content-Type":"application/json"},body:JSON.stringify({texto:v})});
   const d=await r.json();
   const txt=(d.titulo?d.titulo+"\n":"")+(d.linhas||[]).join("\n")+
     (d.escolhas&&d.escolhas.length?"\n"+d.escolhas.map(e=>(e.ativo?"● ":"  ")+e.rotulo+(e.detalhe?"   "+e.detalhe:"")).join("\n"):"");
   responder(txt||"(sem resposta)");aplicarEstado(d.estado);
   if(d.acao==="limpar")limpar();
   return;
  }catch(e){return responder("nao consegui falar com o servidor: "+e)}}
 if(v==="/help")return responder("comandos: "+CMDS.map(c=>c[0]).join("  "));
 if(v==="/status")return responder(`Modo: ${MODES[mode].name} · tokens ${(tokens/1000).toFixed(1)}K/16K · tela: ${emChat?"conversa":"inicial"}`);
 if(v.startsWith("/modo")){const m=v.split(" ")[1];
  if(MODES[m]){setMode(m);responder("modo → "+MODES[m].name)}
  else responder("modos válidos: plan, full, perm");return}
 if(["/agents","/tools","/runs","/config"].includes(v))
  return responder(v.slice(1)+" → painel em breve 🐾");
 responder("comando desconhecido — digite / para ver opções")}

/* ===== stats ===== */
const STATS={plan:[["Turnos:","6",""],["Executadas:","0",""],["Status:","AGUARDANDO","am"]],
 full:[["Turnos:","18",""],["Executadas:","31",""],["Testes:","26/26 ✔","grn"],["Status:","SUCESSO","grn"]],
 perm:[["Turnos:","9",""],["Bloqueadas:","1","rd"],["Status:","AGUARDANDO","am"]]};
function renderStats(m){const base=[["Run ID:","run_2026-08-17_1021",""],["Conexões:","2",""]];
 const f=Math.round(tokens/MAXT*20);
 $("#stats").innerHTML=(base.concat(STATS[m])).map(x=>
  `<div class="row"><span class="k">${x[0]}</span><span class="v ${x[2]}">${x[1]}</span></div>`).join("")+
  "<hr>"+`<div class="row"><span class="k">Contexto:</span><span class="bar"><b>${"█".repeat(f)}</b><i>${"█".repeat(20-f)}</i></span></div>`}

/* ===== atalhos ===== */
document.addEventListener("keydown",e=>{
 if(e.ctrlKey&&e.key.toLowerCase()==="l"){e.preventDefault();return limpar()}
 if(e.target.tagName==="INPUT"||e.ctrlKey||e.altKey)return;
 const k=e.key.toLowerCase();
 if(k==="v")cycleCat();
 if(k==="c")$("#catWrap").classList.toggle("hidden");
 if(k==="s")$("#stats").classList.toggle("hidden");
 if(k==="escape"&&emChat&&!busy)irParaHome()});

/* ===== init ===== */
drawCat();setMode("full");updateBar();verificarServidor();
setInterval(()=>{if(AOVIVO&&!busy)fetch("/api/estado").then(r=>r.json()).then(aplicarEstado).catch(()=>{})},4000);
add("INFO","INFO","Gatinho CLI inicializado com sucesso.");
add("INFO","INFO","digite qualquer mensagem para ver a simulação streaming 🐾");
$("#cmd").focus();
"""


def main():
    gato = "data:image/png;base64," + b64(GATO)
    mini = "data:image/png;base64," + b64(AQUI / "assets" / "gatinho-mini.png")
    corpo = CORPO.replace("__GATO__", gato).replace("__GATO_MINI__", mini)
    html = (f"<!DOCTYPE html>\n<html lang=\"pt-BR\">\n<head>\n"
            f"<meta charset=\"UTF-8\">\n"
            f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
            f"<title>GATINHO CLI — v0.1.0</title>\n<style>{CSS}</style>\n</head>\n<body>\n"
            f"{corpo}\n<script>{JS}</script>\n</body>\n</html>\n")
    SAIDA.write_text(html, encoding="utf-8")
    print(f"gravado: {SAIDA} ({len(html)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
