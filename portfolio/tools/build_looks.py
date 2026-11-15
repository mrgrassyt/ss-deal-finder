"""Builds static/css/looks.css: the Theme Studio looks.

Run:  python tools/build_looks.py
Each look is a token block plus a few rules. Rules are written once with placeholders and come out twice, once for the whole
site (<html data-look="...">) and once for the live preview in the Theme Studio (.sp[data-look="..."]):
  @R            the look itself          @R .btn      anything inside it
  @BODY         the page surface         @BODY::before / ::after   decorative layers (turned off by "background effects")
"""
from pathlib import Path

CARDS = ".feat-item .shot,.feat-item .ph,.explore,.hero-stats li,.pcard .shot,.prow .shot,.lane,.toy-card,.tool,.numbers,.gear,.mini-card,.empty,.lrow .shot,.sp-card"
IMGS = ".shot img,.masonry img,.mini-card img,.cut-main img,.gallery img,.sp-photo"
BTN = ".btn"

LOOKS = {}

def look(key, name, blurb, swatch, tokens, css="", mobile=""):
    LOOKS[key] = dict(name=name, blurb=blurb, swatch=swatch, tokens=tokens, css=css, mobile=mobile)

# ---------------------------------------------------------------------------------------------------------------- aurora
look("aurora", "Aurora", "The current look: a colour for every page, soft glow, glass bars.", ["#ff8a3d", "#ff5f9e", "#a58bff", "#3cc8f4"],
"""--bg:#121315;--bg-deep:#0c0d0e;--panel:#1a1c1f;--panel-2:#212327;--line:rgba(255,255,255,.085);--line-2:rgba(255,255,255,.17);--fg:#edebe6;--mut:#a3a19b;--dim:#74736e;
--acc:#ff8a3d;--acc-soft:rgba(255,138,61,.14);--acc-ink:#1c0e03;--glass:rgba(30,32,36,.58);--glass-line:rgba(255,255,255,.14);--shadow:0 24px 60px -24px rgba(0,0,0,.7);
--r-s:6px;--r-m:12px;--r-l:20px;color-scheme:dark""")

# ------------------------------------------------------------------------------------------------------------ liquid morph
look("liquid-morph", "Liquid Morph", "Soft blobs that melt into each other, pill shapes, springy hovers.", ["#7c4dff", "#00e5ff", "#ff4fd8", "#0b0a1f"],
"""--bg:#0b0a1f;--bg-deep:#070617;--panel:rgba(255,255,255,.07);--panel-2:rgba(255,255,255,.11);--line:rgba(255,255,255,.14);--line-2:rgba(255,255,255,.3);--fg:#f4f2ff;--mut:#bab5e0;--dim:#8c87bb;
--acc:#7cf3ff;--acc-soft:rgba(124,243,255,.16);--acc-ink:#04122a;--glass:rgba(255,255,255,.1);--glass-line:rgba(255,255,255,.26);--shadow:0 30px 80px -30px rgba(124,77,255,.6);
--r-s:12px;--r-m:22px;--r-l:36px;color-scheme:dark""",
"""
@BODY::before{content:"";position:fixed;inset:-25%;z-index:-1;pointer-events:none;filter:blur(46px);opacity:.62;
  background:radial-gradient(38% 38% at 18% 28%,#7c4dff,transparent 62%),radial-gradient(34% 34% at 82% 18%,#00e5ff,transparent 62%),radial-gradient(40% 40% at 62% 88%,#ff4fd8,transparent 62%),radial-gradient(28% 28% at 28% 80%,#3d7bff,transparent 62%);
  animation:lm-morph calc(26s / max(var(--ai,1),.25)) ease-in-out infinite alternate}
@keyframes lm-morph{0%{transform:translate(0,0) rotate(0) scale(1)}50%{transform:translate(calc(var(--ai,1)*4%),calc(var(--ai,1)*-3%)) rotate(calc(var(--ai,1)*14deg)) scale(1.08)}100%{transform:translate(calc(var(--ai,1)*-4%),calc(var(--ai,1)*3%)) rotate(calc(var(--ai,1)*-10deg)) scale(1.02)}}
@R .orb{opacity:0}
@R .hero{background:none}
@R :is(%CARDS%){background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.2);backdrop-filter:blur(20px) saturate(1.4);-webkit-backdrop-filter:blur(20px) saturate(1.4);box-shadow:inset 0 1px 0 rgba(255,255,255,.3),0 24px 60px -30px rgba(0,0,0,.6)}
@R :is(.feat-item .shot,.prow .shot,.pcard .shot,.lrow .shot,.sp-card){border-radius:34px 34px 34px 10px}
@R :is(.feat-item,.explore a,.pcard,.prow,.toy-card,.entry,.lrow,.mini-card,.sp-card){transition:transform .55s cubic-bezier(.34,1.56,.64,1),box-shadow .3s,background .3s}
@R :is(.feat-item,.explore a,.pcard,.toy-card,.mini-card,.sp-card):hover{transform:translateY(-6px) scale(1.025)}
@R .btn{background:linear-gradient(135deg,#7c4dff,#00e5ff);color:#04122a;border-radius:999px;box-shadow:0 12px 30px -10px rgba(0,229,255,.6);transition:transform .45s cubic-bezier(.34,1.56,.64,1),filter .2s}
@R .btn:hover{transform:scale(1.07)}
@R .btn.ghost{background:rgba(255,255,255,.1);color:var(--fg);box-shadow:none;border-color:rgba(255,255,255,.3)}
@R .cut{border-left:0;border-radius:46% 0 0 46% / 34% 0 0 34%;box-shadow:-30px 0 80px -20px rgba(124,77,255,.6)}
@R .nav-in{background:rgba(255,255,255,.12);border-color:rgba(255,255,255,.28)}
@R :is(.chip,.tag,.plain-list li){border-radius:999px}
@R h1,@R .display{background:linear-gradient(100deg,#fff 30%,#bfeaff 60%,#e6c9ff);-webkit-background-clip:text;background-clip:text;color:transparent}
@R .hero h1 span{background:inherit;-webkit-background-clip:inherit;background-clip:inherit}
""")

# -------------------------------------------------------------------------------------------------------------- 3D spatial
look("3d-spatial", "3D Spatial", "Everything floats above the page on its own layer and tilts towards you.", ["#3d5afe", "#ffffff", "#dfe5f0", "#10162b"],
"""--bg:#e6ebf4;--bg-deep:#dbe2ef;--panel:#ffffff;--panel-2:#f1f4fb;--line:rgba(30,40,80,.1);--line-2:rgba(30,40,80,.24);--fg:#10162b;--mut:#4b5473;--dim:#7a83a2;
--acc:#3d5afe;--acc-soft:rgba(61,90,254,.12);--acc-ink:#ffffff;--glass:rgba(255,255,255,.72);--glass-line:rgba(30,40,80,.12);
--shadow:0 1px 0 #fff inset,0 24px 40px -14px rgba(20,30,90,.34),0 60px 100px -50px rgba(20,30,90,.45);--r-s:8px;--r-m:16px;--r-l:26px;color-scheme:light""",
"""
@BODY::before{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;background:radial-gradient(60% 50% at 70% 0,rgba(61,90,254,.14),transparent 70%),radial-gradient(circle at 1px 1px,rgba(30,40,80,.16) 1px,transparent 1.5px) 0 0/26px 26px}
@R .orb{opacity:0}
@R .hero{background:none}
@R main{perspective:1600px}
@R :is(%CARDS%){background:#fff;border:1px solid rgba(30,40,80,.08);box-shadow:var(--shadow);transform-style:preserve-3d}
@R :is(.feat-item,.explore a,.pcard,.prow,.toy-card,.entry,.lrow,.mini-card,.sp-card,.hero-stats li){transition:transform .4s cubic-bezier(.2,.8,.2,1),box-shadow .4s}
@R :is(.feat-item .shot,.pcard .shot,.prow .shot){transform:rotateX(3deg) rotateY(-5deg) translateZ(0)}
@R :is(.feat-item,.pcard,.prow,.toy-card,.sp-card):hover :is(.shot,.ph){transform:rotateX(0) rotateY(0) translateZ(40px) scale(1.03)}
@R :is(.toy-card,.sp-card,.hero-stats li,.mini-card):hover{transform:translateY(-6px) rotateX(5deg) rotateY(-5deg)}
@R .hero-stats li:nth-child(1){transform:translateZ(10px)}@R .hero-stats li:nth-child(2){transform:translateZ(30px)}@R .hero-stats li:nth-child(3){transform:translateZ(50px)}
@R .cut{border-left:0;border-radius:var(--r-l) 0 0 var(--r-l);transform:perspective(1600px) rotateY(-9deg) translateX(2%);transform-origin:100% 50%;box-shadow:-40px 40px 80px -30px rgba(20,30,90,.55)}
@R .btn{box-shadow:0 2px 0 rgba(0,0,0,.25),0 14px 24px -8px rgba(61,90,254,.6),inset 0 1px 0 rgba(255,255,255,.4)}
@R .btn.ghost{background:#fff;border-color:rgba(30,40,80,.18);box-shadow:0 2px 0 rgba(30,40,80,.08),0 10px 20px -10px rgba(20,30,90,.3)}
@R .nav-in{background:rgba(255,255,255,.8);box-shadow:var(--shadow)}
@R .hero h1{text-shadow:0 1px 0 #fff,0 18px 30px rgba(20,30,90,.18)}
@R .tag{background:#fff;box-shadow:0 2px 6px rgba(20,30,90,.1)}
""")

# ---------------------------------------------------------------------------------------------------------------- holographic
look("holographic", "Holographic", "Iridescent foil: colours that shift as the light moves across them.", ["#ff6ec7", "#7873ff", "#00e5ff", "#7dffb2"],
"""--bg:#07060e;--bg-deep:#04030a;--panel:rgba(255,255,255,.045);--panel-2:rgba(255,255,255,.08);--line:rgba(255,255,255,.12);--line-2:rgba(255,255,255,.26);--fg:#f7f4ff;--mut:#b6b0d2;--dim:#857fa6;
--acc:#a99bff;--acc-soft:rgba(169,155,255,.16);--acc-ink:#0b0720;--glass:rgba(20,16,40,.6);--glass-line:rgba(255,255,255,.2);--shadow:0 30px 70px -30px rgba(120,100,255,.5);
--r-s:8px;--r-m:16px;--r-l:24px;--holo:linear-gradient(115deg,#ff6ec7,#7873ff 25%,#00e5ff 50%,#7dffb2 70%,#ffe36e 85%,#ff6ec7);color-scheme:dark""",
"""
@BODY::before{content:"";position:fixed;inset:-20%;z-index:-1;pointer-events:none;opacity:.5;filter:blur(60px);
  background:conic-gradient(from 0deg at 30% 30%,#ff6ec7,#7873ff,#00e5ff,#7dffb2,#ffe36e,#ff6ec7);animation:holo-spin calc(40s / max(var(--ai,1),.25)) linear infinite}
@keyframes holo-spin{to{filter:blur(60px) hue-rotate(360deg)}}
@BODY::after{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;background:rgba(7,6,14,.78)}
@R .orb{opacity:0}
@R .hero{background:none}
@R :is(%CARDS%){border:1.5px solid transparent;background:linear-gradient(#0d0b1c,#0d0b1c) padding-box,var(--holo) border-box;background-size:auto,300% 100%;transition:background-position .8s,transform .3s}
@R :is(%CARDS%):hover{background-position:0 0,100% 0}
@R .btn{background:var(--holo);background-size:300% 100%;color:#10082a;animation:holo-slide calc(8s / max(var(--ai,1),.25)) linear infinite}
@keyframes holo-slide{to{background-position:300% 0}}
@R .btn.ghost{background:transparent;color:var(--fg);animation:none;border:1.5px solid transparent;background:linear-gradient(#0d0b1c,#0d0b1c) padding-box,var(--holo) border-box}
@R h1,@R .display{background:var(--holo);background-size:250% 100%;-webkit-background-clip:text;background-clip:text;color:transparent;animation:holo-slide calc(14s / max(var(--ai,1),.25)) linear infinite}
@R .hero h1 span{background:inherit;-webkit-background-clip:inherit;background-clip:inherit}
@R .cut{border-left:0;border-image:var(--holo) 1;border-left:6px solid;border-image-slice:1}
@R .cut::after{background:linear-gradient(115deg,rgba(255,110,199,.28),transparent 40%,rgba(0,229,255,.25))}
@R .hero-stats b{background:var(--holo);-webkit-background-clip:text;background-clip:text;color:transparent}
@R .nav-in{border:1.5px solid transparent;background:linear-gradient(rgba(14,11,30,.85),rgba(14,11,30,.85)) padding-box,var(--holo) border-box}
""")

# --------------------------------------------------------------------------------------------------------------- cyberpunk
look("cyberpunk-neon", "Cyberpunk Neon", "Black glass, neon yellow, cut corners, a little glitch.", ["#fcee09", "#ff2bd6", "#00f0ff", "#0a0510"],
"""--bg:#09040f;--bg-deep:#05020a;--panel:#140a20;--panel-2:#1d1030;--line:rgba(255,43,214,.32);--line-2:rgba(0,240,255,.55);--fg:#f6f1ff;--mut:#b9a6da;--dim:#8068aa;
--acc:#fcee09;--acc-soft:rgba(252,238,9,.14);--acc-ink:#0a0510;--glass:rgba(16,6,28,.78);--glass-line:rgba(0,240,255,.5);--shadow:0 0 0 1px rgba(0,240,255,.4),0 0 40px -8px rgba(255,43,214,.45);
--r-s:0;--r-m:2px;--r-l:2px;color-scheme:dark""",
"""
@BODY::before{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;background:linear-gradient(rgba(0,240,255,.07) 1px,transparent 1px) 0 0/48px 48px,linear-gradient(90deg,rgba(255,43,214,.07) 1px,transparent 1px) 0 0/48px 48px,radial-gradient(70% 50% at 80% 0,rgba(255,43,214,.22),transparent 70%)}
@BODY::after{content:"";position:fixed;inset:0;z-index:70;pointer-events:none;background:repeating-linear-gradient(0deg,rgba(0,0,0,.28) 0 1px,transparent 1px 3px);mix-blend-mode:multiply}
@R .orb{opacity:0}
@R .hero{background:none}
@R :is(h1,h2,h3,.display,.btn,.chip,.status){text-transform:uppercase;font-stretch:62%;letter-spacing:.02em}
@R h1,@R .display{text-shadow:2px 0 #ff2bd6,-2px 0 #00f0ff;animation:cy-glitch calc(5s / max(var(--ai,1),.25)) steps(1) infinite}
@keyframes cy-glitch{0%,92%,100%{text-shadow:2px 0 #ff2bd6,-2px 0 #00f0ff}93%{text-shadow:calc(6px*var(--ai,1)) 0 #ff2bd6,calc(-6px*var(--ai,1)) 0 #00f0ff;transform:translateX(calc(2px*var(--ai,1)))}95%{text-shadow:-4px 0 #ff2bd6,4px 0 #00f0ff;transform:none}}
@R .btn{background:var(--acc);color:#0a0510;border-radius:0;clip-path:polygon(0 0,calc(100% - 14px) 0,100% 14px,100% 100%,14px 100%,0 calc(100% - 14px));font-weight:800;border:0;padding-inline:26px}
@R .btn.ghost{background:transparent;color:#00f0ff;box-shadow:inset 0 0 0 1px #00f0ff;backdrop-filter:none}
@R :is(%CARDS%){background:rgba(20,10,32,.85);border:1px solid #00f0ff;box-shadow:0 0 22px -8px rgba(0,240,255,.55),inset 0 0 30px -18px #ff2bd6;clip-path:polygon(0 0,calc(100% - 16px) 0,100% 16px,100% 100%,16px 100%,0 calc(100% - 16px))}
@R .cut{border-left:6px solid #ff2bd6;clip-path:polygon(7% 0,100% 0,100% 100%,0 100%)}
@R .cut-main img{filter:saturate(1.3) contrast(1.15)}
@R .hero-stats b{color:#00f0ff;text-shadow:0 0 14px rgba(0,240,255,.7)}
@R .nav-in{border-radius:0;border:1px solid #00f0ff;clip-path:polygon(0 0,calc(100% - 14px) 0,100% 14px,100% 100%,14px 100%,0 calc(100% - 14px))}
@R :is(.tag,.chip){border-radius:0;border-color:#ff2bd6}
@R .hero-name{color:#00f0ff}
""")

# ---------------------------------------------------------------------------------------------------------------- wireframe
look("wireframe-3d", "Wireframe 3D", "Everything is an outline: edges only, with a grid floor receding into the distance.", ["#7ee8ff", "#05070a", "#dff7ff", "#2c6e80"],
"""--bg:#04060a;--bg-deep:#020306;--panel:transparent;--panel-2:rgba(126,232,255,.06);--line:rgba(126,232,255,.3);--line-2:rgba(126,232,255,.7);--fg:#dff7ff;--mut:#8fc9d8;--dim:#5b8f9d;
--acc:#7ee8ff;--acc-soft:rgba(126,232,255,.14);--acc-ink:#031016;--glass:rgba(4,8,12,.8);--glass-line:rgba(126,232,255,.6);--shadow:none;--r-s:0;--r-m:0;--r-l:0;
--sans:"Martian Mono",ui-monospace,Consolas,monospace;color-scheme:dark""",
"""
@BODY{font-size:15px}
@BODY::before{content:"";position:fixed;left:-50%;right:-50%;bottom:0;height:62vh;z-index:-1;pointer-events:none;transform:perspective(420px) rotateX(62deg);transform-origin:50% 100%;
  background:linear-gradient(rgba(126,232,255,.5) 1px,transparent 1px) 0 0/64px 64px,linear-gradient(90deg,rgba(126,232,255,.5) 1px,transparent 1px) 0 0/64px 64px;
  -webkit-mask-image:linear-gradient(transparent,#000 60%);mask-image:linear-gradient(transparent,#000 60%);animation:wf-run calc(6s / max(var(--ai,1),.25)) linear infinite}
@keyframes wf-run{to{background-position:0 64px,0 0}}
@R .orb{opacity:0}
@R .hero{background:none}
@R :is(%CARDS%){background:transparent;border:1px solid var(--line-2);box-shadow:none;backdrop-filter:none}
@R :is(%CARDS%):hover{background:rgba(126,232,255,.07);border-color:#7ee8ff}
@R :is(%IMGS%){filter:grayscale(1) contrast(1.25) brightness(.9);mix-blend-mode:luminosity}
@R :is(.shot,.mini-card,.cut,.sp-photo){background:#04222b}
@R h1,@R .display{color:transparent;-webkit-text-stroke:1px var(--fg);letter-spacing:-.01em}
@R .hero h1 span{-webkit-text-stroke:1px var(--fg)}
@R :is(h2,h3){font-weight:500}
@R .btn{background:transparent;color:var(--acc);border:1px solid var(--acc);border-radius:0;box-shadow:0 0 0 3px var(--bg),0 0 0 4px var(--line)}
@R .btn:hover{background:var(--acc);color:var(--acc-ink)}
@R .nav-in{border-radius:0;box-shadow:none}
@R .hero-stats b{font-weight:500;-webkit-text-stroke:0}
@R .cut{border-left:1px solid var(--acc)}
@R :is(.tag,.chip){border-radius:0}
""")

# --------------------------------------------------------------------------------------------------------------- retro VHS
look("retro-vhs", "Retro VHS", "A tape from 1994: scanlines, colour fringes, a tracking glitch.", ["#ff4fa0", "#2ee6d6", "#ffb347", "#15101f"],
"""--bg:#15101f;--bg-deep:#0e0a16;--panel:#1f1830;--panel-2:#2a2140;--line:rgba(245,233,217,.14);--line-2:rgba(245,233,217,.32);--fg:#f6ead8;--mut:#c1b0d2;--dim:#8c7ca3;
--acc:#ff4fa0;--acc-soft:rgba(255,79,160,.16);--acc-ink:#19040f;--glass:rgba(31,24,48,.78);--glass-line:rgba(245,233,217,.22);--shadow:0 20px 50px -20px rgba(0,0,0,.8);
--r-s:3px;--r-m:6px;--r-l:10px;--sans:"Martian Mono",ui-monospace,Consolas,monospace;color-scheme:dark""",
"""
@BODY{font-size:15px}
@BODY::before{content:"";position:fixed;inset:0;z-index:70;pointer-events:none;
  background:repeating-linear-gradient(0deg,rgba(0,0,0,.26) 0 2px,transparent 2px 4px),radial-gradient(120% 90% at 50% 40%,transparent 55%,rgba(0,0,0,.55))}
@BODY::after{content:"";position:fixed;left:0;right:0;height:14vh;z-index:71;pointer-events:none;top:-20vh;background:linear-gradient(transparent,rgba(255,255,255,.07),transparent);animation:vhs-track calc(7s / max(var(--ai,1),.25)) linear infinite}
@keyframes vhs-track{to{top:110vh}}
@R .orb{opacity:0}
@R .hero{background:radial-gradient(70% 60% at 20% 20%,rgba(255,79,160,.2),transparent 70%),radial-gradient(60% 60% at 80% 90%,rgba(46,230,214,.16),transparent 70%)}
@R h1,@R .display,@R h2{text-shadow:-2px 0 rgba(46,230,214,.7),2px 0 rgba(255,79,160,.7)}
@R :is(h1,.display){font-stretch:80%;font-weight:700;letter-spacing:-.03em}
@R :is(%IMGS%){filter:contrast(1.12) saturate(1.3) sepia(.18)}
@R .btn{background:#f6ead8;color:#15101f;border-radius:2px;text-transform:uppercase;letter-spacing:.08em;font-size:.8rem;box-shadow:3px 3px 0 var(--acc)}
@R .btn.ghost{background:transparent;color:var(--fg);box-shadow:3px 3px 0 var(--line-2)}
@R .btn:hover{transform:translate(-1px,-1px);box-shadow:5px 5px 0 var(--acc)}
@R :is(%CARDS%){border:1px solid var(--line-2);box-shadow:4px 4px 0 rgba(255,79,160,.35)}
@R .hero-name::after{content:"  ▶ PLAY";color:var(--acc);font-size:.78rem;letter-spacing:.1em}
@R .hero-stats b{color:#2ee6d6;text-shadow:-1px 0 #ff4fa0}
@R .cut{border-left:6px solid #2ee6d6}
@R .nav-in{border-radius:4px}
""")

# --------------------------------------------------------------------------------------------------------- minimal editorial
look("minimal-editorial", "Minimal Editorial", "A printed page: serif headlines, hairlines, one ink colour, lots of air.", ["#111111", "#1d3fd1", "#f7f7f4", "#c9c9c2"],
"""--bg:#f7f7f4;--bg-deep:#efefea;--panel:#ffffff;--panel-2:#eeeee8;--line:rgba(17,17,17,.16);--line-2:rgba(17,17,17,.5);--fg:#111111;--mut:#565651;--dim:#85857e;
--acc:#1d3fd1;--acc-soft:rgba(29,63,209,.1);--acc-ink:#ffffff;--glass:rgba(247,247,244,.9);--glass-line:rgba(17,17,17,.2);--shadow:none;--r-s:0;--r-m:0;--r-l:0;
--serif:ui-serif,"Iowan Old Style","Palatino Linotype",Palatino,Georgia,"Times New Roman",serif;color-scheme:light""",
"""
@R .orb{opacity:0}
@R .hero{background:none}
@R :is(h1,h2,h3,.display,.hero-stats b,.numbers b){font-family:var(--serif);font-stretch:100%;font-weight:500;letter-spacing:-.02em;line-height:1.04}
@R h1{font-size:clamp(2.8rem,6.6vw,5.6rem)}
@R .hero h1{font-size:clamp(2.8rem,6vw,5.4rem)}
@R :is(%CARDS%){background:transparent;border:0;border-top:1px solid var(--fg);box-shadow:none;backdrop-filter:none}
@R :is(.explore,.numbers,.gear,.hero-stats li,.mini-card,.sp-card){border:1px solid var(--line)}
@R .explore{border-top:2px solid var(--fg)}
@R .explore a{background:transparent}
@R .explore a:hover{background:#fff}
@R .btn{background:var(--fg);color:#fff;border-radius:0;font-weight:500;padding-inline:26px}
@R .btn.ghost{background:transparent;color:var(--fg);border:0;border-bottom:1px solid var(--fg);padding-inline:2px;backdrop-filter:none}
@R .nav-in{border-radius:0;background:rgba(247,247,244,.92);border:0;border-bottom:1px solid var(--fg);box-shadow:none}
@R .cut{border-left:1px solid var(--fg)}
@R .cut::after{display:none}
@R .hero-stats b{color:var(--fg);font-size:2.4rem}
@R .hero-name{font-style:italic;font-family:var(--serif)}
@R .hero-name::before{display:none}
@R :is(.tag,.chip,.plain-list li){border-radius:0}
@R .page-head h1::after{height:2px;width:90px;border-radius:0;background:var(--fg)}
@R .prose{font-family:var(--serif);font-size:1.14rem}
""")

# -------------------------------------------------------------------------------------------------------------------- clay
look("clay-3d", "Clay 3D", "Soft, chunky and pastel, as if everything was pressed from modelling clay.", ["#ff7ab8", "#ffd45e", "#7fd6ff", "#ece4f7"],
"""--bg:#ece4f7;--bg-deep:#e2d8f1;--panel:#f4effb;--panel-2:#e9e0f5;--line:rgba(110,90,160,.12);--line-2:rgba(110,90,160,.28);--fg:#2b2342;--mut:#645a86;--dim:#8d84ab;
--acc:#ff6fb1;--acc-soft:rgba(255,111,177,.18);--acc-ink:#3a0a24;--glass:rgba(244,239,251,.85);--glass-line:rgba(255,255,255,.7);
--clay:10px 12px 26px rgba(120,100,170,.3),-8px -8px 22px rgba(255,255,255,.95),inset 0 -6px 12px rgba(120,100,170,.14),inset 0 6px 12px rgba(255,255,255,.75);
--shadow:var(--clay);--r-s:14px;--r-m:24px;--r-l:36px;color-scheme:light""",
"""
@R .orb{opacity:0}
@R .hero{background:none}
@R :is(h1,h2,h3,.display){font-weight:800;font-stretch:104%;letter-spacing:-.025em}
@R .hero h1{font-stretch:92%}
@R :is(%CARDS%){background:var(--panel);border:0;box-shadow:var(--clay);backdrop-filter:none}
@R .explore{padding:14px;gap:14px;background:transparent;border:0;box-shadow:none}
@R .explore a{border-radius:var(--r-m);box-shadow:var(--clay);border:0;background:var(--panel)}
@R .explore a::before{display:none}
@R .explore a:nth-child(5n+1){background:#ffd9e8}@R .explore a:nth-child(5n+2){background:#ffeab0}@R .explore a:nth-child(5n+3){background:#cdeeff}
@R .explore a:nth-child(5n+4){background:#d7f5d2}@R .explore a:nth-child(5n+5){background:#e2d6ff}
@R :is(.feat-item,.explore a,.pcard,.toy-card,.mini-card,.sp-card,.hero-stats li){transition:transform .35s cubic-bezier(.34,1.56,.64,1),box-shadow .3s}
@R :is(.feat-item,.explore a,.pcard,.toy-card,.mini-card,.sp-card,.hero-stats li):hover{transform:translateY(-5px) scale(1.02)}
@R .btn{background:var(--acc);color:var(--acc-ink);border:0;border-radius:999px;font-weight:800;padding:13px 26px;box-shadow:8px 10px 20px rgba(255,111,177,.4),-6px -6px 14px rgba(255,255,255,.8),inset 0 -5px 10px rgba(160,40,100,.25),inset 0 5px 10px rgba(255,255,255,.5)}
@R .btn.ghost{background:var(--panel);color:var(--fg);box-shadow:var(--clay);backdrop-filter:none}
@R .btn:active{box-shadow:inset 6px 6px 12px rgba(160,40,100,.3),inset -6px -6px 12px rgba(255,255,255,.4)}
@R .nav-in{background:var(--panel);border:0;box-shadow:var(--clay)}
@R .cut{border-left:0;border-radius:var(--r-l) 0 0 var(--r-l);width:44%;top:96px;bottom:36px;box-shadow:var(--clay)}
@R .cut::after{display:none}
@R :is(.shot,.ph){border:0}
@R .hero-stats b{color:var(--acc)}
@R :is(.tag,.chip,.plain-list li){border:0;box-shadow:var(--clay);background:var(--panel);border-radius:999px}
@R .input,@R .field :is(input,textarea,select){border:0;background:var(--panel-2);box-shadow:inset 4px 4px 9px rgba(120,100,170,.22),inset -4px -4px 9px rgba(255,255,255,.9)}
""", mobile="@R .cut{top:auto;bottom:auto;border-radius:var(--r-l);margin:0 16px 24px;width:auto}")

# ----------------------------------------------------------------------------------------------------------------- blueprint
look("blueprint", "Blueprint", "White lines on drawing-paper blue: grid, dashes and labelled dimensions.", ["#0d3b8c", "#ffffff", "#7fe3ff", "#0a2f70"],
"""--bg:#0d3b8c;--bg-deep:#0a2f70;--panel:rgba(255,255,255,.05);--panel-2:rgba(255,255,255,.1);--line:rgba(255,255,255,.26);--line-2:rgba(255,255,255,.6);--fg:#eaf3ff;--mut:#b2cdf6;--dim:#86a8dd;
--acc:#8fe6ff;--acc-soft:rgba(143,230,255,.16);--acc-ink:#05224f;--glass:rgba(10,47,112,.85);--glass-line:rgba(255,255,255,.55);--shadow:none;--r-s:0;--r-m:0;--r-l:0;
--sans:"Martian Mono",ui-monospace,Consolas,monospace;color-scheme:dark""",
"""
@BODY{font-size:15px}
@BODY::before{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;
  background:linear-gradient(rgba(255,255,255,.16) 1px,transparent 1px) 0 0/120px 120px,linear-gradient(90deg,rgba(255,255,255,.16) 1px,transparent 1px) 0 0/120px 120px,
  linear-gradient(rgba(255,255,255,.07) 1px,transparent 1px) 0 0/24px 24px,linear-gradient(90deg,rgba(255,255,255,.07) 1px,transparent 1px) 0 0/24px 24px}
@R .orb{opacity:0}
@R .hero{background:none}
@R :is(h1,h2,h3,.display){font-stretch:90%;font-weight:600;letter-spacing:-.03em}
@R :is(%CARDS%){background:rgba(13,59,140,.55);border:1px dashed var(--line-2);box-shadow:none;backdrop-filter:none}
@R .explore a,@R .explore{border-style:dashed}
@R :is(%IMGS%){filter:grayscale(1) contrast(1.15) brightness(1.05);mix-blend-mode:luminosity;opacity:.92}
@R :is(.shot,.mini-card,.sp-card .sp-photo,.cut){background:#0a2f70}
@R .btn{background:transparent;color:#fff;border:1px solid #fff;border-radius:0;box-shadow:inset 0 0 0 3px var(--bg),inset 0 0 0 4px rgba(255,255,255,.5)}
@R .btn:hover{background:#fff;color:#0d3b8c}
@R .nav-in{border-radius:0;border:1px dashed #fff;box-shadow:none}
@R .cut{border-left:1px dashed #fff}
@R .hero-name::before{border-radius:0;transform:rotate(45deg)}
@R .section-head{border-bottom:1px dashed var(--line-2);padding-bottom:10px}
@R :is(.tag,.chip,.plain-list li){border-radius:0;border-style:dashed}
@R .hero-stats b{color:#fff}
""")

# ---------------------------------------------------------------------------------------------------------- ASCII / terminal
look("ascii-terminal", "ASCII Terminal", "Green phosphor on black, monospace everywhere, brackets around the buttons.", ["#5dff5d", "#b6ffb0", "#2b7a2b", "#050805"],
"""--bg:#040704;--bg-deep:#020402;--panel:#081108;--panel-2:#0d1a0d;--line:rgba(93,255,93,.22);--line-2:rgba(93,255,93,.5);--fg:#b6ffb0;--mut:#6fc66a;--dim:#3f8a3b;
--acc:#5dff5d;--acc-soft:rgba(93,255,93,.14);--acc-ink:#021002;--glass:rgba(4,10,4,.88);--glass-line:rgba(93,255,93,.5);--shadow:none;--r-s:0;--r-m:0;--r-l:0;
--sans:"Martian Mono",ui-monospace,Consolas,monospace;color-scheme:dark""",
"""
@BODY{font-size:14.5px;text-shadow:0 0 6px rgba(93,255,93,.28)}
@BODY::before{content:"";position:fixed;inset:0;z-index:70;pointer-events:none;background:repeating-linear-gradient(0deg,rgba(0,0,0,.3) 0 1px,transparent 1px 3px),radial-gradient(120% 100% at 50% 50%,transparent 60%,rgba(0,0,0,.6))}
@R .orb{opacity:0}
@R .hero{background:none}
@R :is(h1,.display){font-stretch:75%;font-weight:700;letter-spacing:-.04em}
@R .hero h1 span:last-child::after{content:"_";margin-left:4px;animation:tm-blink 1s steps(1) infinite}
@keyframes tm-blink{50%{opacity:0}}
@R h2::before{content:"> ";color:var(--acc)}
@R :is(%IMGS%){filter:grayscale(1) contrast(1.25) brightness(.85) sepia(1) hue-rotate(58deg) saturate(2.4)}
@R :is(%CARDS%){background:transparent;border:1px solid var(--line-2);box-shadow:none;backdrop-filter:none}
@R :is(%CARDS%):hover{background:rgba(93,255,93,.06)}
@R .btn{background:transparent;color:var(--acc);border:0;border-radius:0;padding-inline:4px;font-weight:700}
@R .btn::before{content:"[ "}@R .btn::after{content:" ]"}
@R .btn:hover{background:var(--acc);color:var(--acc-ink);filter:none}
@R .nav-in{border-radius:0;border:1px solid var(--line-2);background:rgba(4,10,4,.92);box-shadow:none}
@R .cut{border-left:1px solid var(--acc)}
@R .hero-name::before{content:"$";width:auto;height:auto;background:none;box-shadow:none;color:var(--acc)}
@R :is(.tag,.chip,.plain-list li){border-radius:0}
@R .hero-stats b{font-weight:700}
@R .brand svg{filter:grayscale(1) brightness(1.5)}
""")

# ------------------------------------------------------------------------------------------------------------------ build
def split_top(css):
    """Yield (header, body) for every top-level block, brace-matched."""
    i, n = 0, len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            break
        head, depth, k = css[i:j].strip(), 1, j + 1
        while k < n and depth:
            depth += {"{": 1, "}": -1}.get(css[k], 0)
            k += 1
        yield head, css[j + 1:k - 1]
        i = k


def expand(head, key):
    root = f':root[data-look="{key}"]'
    prev = f'.sp[data-look="{key}"]'
    out = []
    for part in head.split(","):
        part = part.strip()
        if "%" in part:
            part = part.replace("%CARDS%", CARDS).replace("%IMGS%", IMGS)
        if part.startswith("@BODY"):
            rest = part[5:]
            out.append(f"{root} body{rest}" if not rest.startswith("::") else f"{root} body{rest}")
            out.append(f"{prev}{rest}")
        elif part.startswith("@R"):
            rest = part[2:]
            out.append(f"{root}{rest}")
            out.append(f"{prev}{rest}")
        else:
            out.append(part)
    return ",".join(out)


def rules(css, key):
    res = []
    for head, body in split_top(css):
        if head.startswith("@keyframes"):
            res.append(f"{head}{{{body}}}")
            continue
        res.append(f"{expand(head, key)}{{{body}}}")
    return "\n".join(res)


def split_cards(css):
    # `:is(%CARDS%)` expands inside the selector; the placeholder is substituted before splitting commas
    return css.replace("%CARDS%", CARDS).replace("%IMGS%", IMGS)


def build():
    out = ["/* Theme Studio looks. Generated by tools/build_looks.py: edit that file, not this one. */",
           "/* A look is switched with <html data-look=\"name\">; the studio preview uses .sp[data-look]. */",
           ".sp{position:relative;isolation:isolate;overflow:hidden;background:var(--bg);color:var(--fg);font:400 15px/1.5 var(--sans)}",
           ".sp .nav-in{view-transition-name:none}",
           ".sp[data-look]::before,.sp[data-look]::after{position:absolute!important}",
           ":root{--ai:1}"]
    for key, L in LOOKS.items():
        tokens = L["tokens"].replace("\n", "")
        sel = f'.sp[data-look="{key}"]' if key == "aurora" else f':root[data-look="{key}"],.sp[data-look="{key}"]'   # Aurora's tokens are the site's own (dark and light)
        out.append(f'{sel}{{{tokens}}}')
        css = split_cards(L["css"])
        # protect commas inside :is(...) when splitting selector lists: expand per top-level comma only
        out.append(rules_safe(css, key))
        if L["mobile"]:
            out.append("@media (max-width:820px){" + rules_safe(split_cards(L["mobile"]), key) + "}")
    out.append(COMMON)
    return "\n".join(out) + "\n"


def rules_safe(css, key):
    res = []
    for head, body in split_top(css):
        if head.startswith("@keyframes"):
            res.append(f"{head}{{{body}}}")
            continue
        # split on commas not inside parentheses
        parts, depth, cur = [], 0, ""
        for ch in head:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if ch == "," and depth == 0:
                parts.append(cur); cur = ""
            else:
                cur += ch
        parts.append(cur)
        res.append(",".join(_one(p.strip(), key) for p in parts) + f"{{{body}}}")
    return "\n".join(res)


def _one(part, key):
    root, prev = f':root[data-look="{key}"]', f'.sp[data-look="{key}"]'
    if part.startswith("@BODY"):
        rest = part[5:]
        return f"{root} body{rest},{prev}{rest}"
    if part.startswith("@R"):
        rest = part[2:]
        return f"{root}{rest},{prev}{rest}"
    return part


COMMON = """
/* every look except Aurora drops the page glow and the per-page colours; the day/night switch belongs to Aurora */
:root:not([data-look="aurora"]) main::before{display:none}
:root:not([data-look="aurora"]) #theme-btn{display:none}
/* controls from the Theme Studio */
:root[data-anim="off"] *,:root[data-anim="off"] *::before,:root[data-anim="off"] *::after,
:root[data-motion="reduced"] *,:root[data-motion="reduced"] *::before,:root[data-motion="reduced"] *::after{animation:none!important;transition:none!important}
:root[data-fx="off"] body::before,:root[data-fx="off"] body::after,:root[data-fx="off"] .orb,.sp[data-fx="off"]::before,.sp[data-fx="off"]::after{display:none!important}
:root[data-3d="off"] :is(%CARDS%,.cut,.hero-stats li,main),.sp[data-3d="off"] :is(%CARDS%,.cut,.hero-stats li,.shot){transform:none!important;perspective:none!important}
:root[data-3d="off"] .cut-main img{transform:none}
:root[data-perf="on"] *,.sp[data-perf="on"] *{backdrop-filter:none!important;-webkit-backdrop-filter:none!important;text-shadow:none!important}
:root[data-perf="on"] *,:root[data-perf="on"] *::before,:root[data-perf="on"] *::after{animation:none!important}
:root[data-perf="on"] body::before,:root[data-perf="on"] body::after,:root[data-perf="on"] .orb,.sp[data-perf="on"]::before,.sp[data-perf="on"]::after{display:none!important}
"""
COMMON = COMMON.replace("%CARDS%", CARDS)


if __name__ == "__main__":
    target = Path(__file__).resolve().parent.parent / "static" / "css" / "looks.css"
    target.write_text(build(), encoding="utf-8")
    print(f"{target}: {target.stat().st_size} bytes, {len(LOOKS)} looks")
    import json
    (Path(__file__).resolve().parent / "looks.json").write_text(json.dumps({k: {"name": v["name"], "blurb": v["blurb"], "swatch": v["swatch"]} for k, v in LOOKS.items()}, indent=1, ensure_ascii=False))
