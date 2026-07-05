"""读取 JSON 数据 -> 生成静态 index.html（JSON + 地图 GeoJSON 内嵌，可双击打开）。

用法:
  python3 build_site.py                       # 默认读 data/shops.json
  python3 build_site.py data/shops_small.json # 指定数据源
"""
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_DATA = os.path.join(ROOT, "data", "shops.json")
GEO_PATH = os.path.join(HERE, "china_geo.min.json")
OUT_HTML = os.path.join(ROOT, "index.html")

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>隋坡探店地图</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
  :root{
    --bg:#faf7f2; --panel:#ffffff; --ink:#2b2622; --muted:#8a8079;
    --line:#ece6dd; --accent:#c0392b; --accent2:#e8732c;
    --amber:#b9791f; --amber-bg:#fdf3e0; --green:#3f8f5b;
    --radius:14px; --shadow:0 1px 2px rgba(60,40,20,.05),0 6px 20px rgba(60,40,20,.06);
  }
  *{box-sizing:border-box}
  html,body{margin:0}
  body{
    background:var(--bg); color:var(--ink);
    font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;
    line-height:1.55; -webkit-font-smoothing:antialiased;
  }
  a{color:inherit; text-decoration:none}
  .wrap{max-width:1180px; margin:0 auto; padding:0 20px 80px}
  header.hero{ background:linear-gradient(135deg,#2b1d16,#4a2c1c); color:#fff; padding:34px 20px 30px;}
  header.hero .wrap{padding:0}
  header.hero h1{margin:0; font-size:28px; font-weight:800; letter-spacing:.5px}
  header.hero h1 .pin{color:var(--accent2)}
  header.hero p{margin:8px 0 0; color:#e9ddcf; font-size:14px}
  .stats{display:flex; flex-wrap:wrap; gap:10px; margin-top:18px}
  .stat{background:rgba(255,255,255,.10); border:1px solid rgba(255,255,255,.14);
        padding:8px 14px; border-radius:10px; font-size:13px; color:#f3ece2}
  .stat b{font-size:18px; font-weight:800; color:#fff; margin-right:5px}

  .bar{position:sticky; top:0; z-index:20; background:rgba(250,247,242,.92);
       backdrop-filter:blur(8px); border-bottom:1px solid var(--line); padding:12px 0}
  .controls{display:flex; flex-wrap:wrap; gap:10px; align-items:center}
  .controls input[type=text]{flex:1 1 240px; min-width:180px; padding:10px 14px;
       border:1px solid var(--line); border-radius:10px; font-size:14px; background:#fff}
  .controls select,.toggle{padding:10px 12px; border:1px solid var(--line);
       border-radius:10px; background:#fff; font-size:14px; cursor:pointer; color:var(--ink)}
  .toggle.on{background:var(--accent); color:#fff; border-color:var(--accent)}
  .toggle.amber.on{background:var(--amber); border-color:var(--amber)}
  .seg{display:inline-flex; border:1px solid var(--line); border-radius:10px; overflow:hidden; background:#fff}
  .seg button{border:0; background:#fff; padding:10px 14px; font-size:14px; cursor:pointer; color:var(--ink)}
  .seg button.on{background:var(--accent); color:#fff}
  .result-count{font-size:13px; color:var(--muted); margin-left:auto}

  .locchart{display:flex; flex-wrap:wrap; gap:6px 18px; margin:16px 0 4px}
  .locbar{display:flex; align-items:center; gap:8px; font-size:12px; color:var(--muted)}
  .locbar .track{width:90px; height:7px; background:#efe8de; border-radius:4px; overflow:hidden}
  .locbar .fill{height:100%; background:linear-gradient(90deg,var(--accent),var(--accent2))}
  .locbar b{color:var(--ink)}

  /* 地图视图 */
  .mapview{margin-top:18px}
  #map{width:100%; height:560px; background:#fff; border:1px solid var(--line);
       border-radius:var(--radius); box-shadow:var(--shadow)}
  .mapbar{display:flex; align-items:center; gap:14px; flex-wrap:wrap; margin:10px 2px 0}
  .legend{display:flex; align-items:center; gap:8px; font-size:12px; color:var(--muted)}
  .legend .ramp{display:flex; gap:2px}
  .legend .ramp i{display:block; width:18px; height:12px; border-radius:2px}
  .mapbar .hint{font-size:12px; color:var(--muted)}
  #mapfallback{display:none; padding:40px; text-align:center; color:var(--muted);
       background:#fff; border:1px solid var(--line); border-radius:var(--radius)}

  .grid{display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:16px; margin-top:18px}
  .card{background:var(--panel); border:1px solid var(--line); border-radius:var(--radius);
        overflow:hidden; box-shadow:var(--shadow); display:flex; flex-direction:column; transition:transform .12s}
  .card:hover{transform:translateY(-2px)}
  .card .cover{position:relative; aspect-ratio:16/9; background:#eee; overflow:hidden}
  .card .cover img{width:100%; height:100%; object-fit:cover; display:block}
  .pill{position:absolute; top:8px; left:8px; padding:3px 9px; border-radius:999px;
        font-size:11px; font-weight:700; color:#fff; backdrop-filter:blur(2px)}
  .pill.tandian{background:rgba(192,57,43,.92)}
  .pill.other{background:rgba(90,84,78,.85)}
  .conf{position:absolute; top:8px; right:8px; padding:3px 9px; border-radius:999px;
        font-size:10px; font-weight:700; background:rgba(255,255,255,.9); color:var(--ink)}
  .conf.low{color:var(--amber)} .conf.medium{color:#9a7b1f}
  .body{padding:12px 14px 14px; display:flex; flex-direction:column; gap:8px; flex:1}
  .shop{font-size:17px; font-weight:800; line-height:1.3}
  .shop.missing{color:var(--amber)}
  .vtitle{font-size:12.5px; color:var(--muted); display:-webkit-box; -webkit-line-clamp:2;
          -webkit-box-orient:vertical; overflow:hidden}
  .meta{display:flex; align-items:center; gap:8px; font-size:12px; color:var(--muted); flex-wrap:wrap}
  .loc{display:inline-flex; align-items:center; gap:4px; background:#f1ebe1;
       color:#7a4b22; padding:3px 9px; border-radius:8px; font-weight:600; font-size:12px}
  .loc.unknown{background:#f0eee9; color:var(--muted)}
  .plays::before{content:"▶ "; color:var(--accent)}
  .note{font-size:12px; color:#8a5a12; background:var(--amber-bg); border:1px solid #f0dcae;
        border-radius:8px; padding:7px 9px}
  .card .foot{margin-top:auto}
  .openlink{display:inline-block; font-size:12px; color:var(--accent); font-weight:600; margin-top:2px}
  .openlink::after{content:" ↗"}
  .empty{text-align:center; color:var(--muted); padding:60px 20px; font-size:14px}
  footer{margin-top:40px; font-size:12px; color:var(--muted); text-align:center; line-height:1.8}
  @media (max-width:560px){.grid{grid-template-columns:1fr} #map{height:420px}}
</style>
</head>
<body>
<header class="hero">
  <div class="wrap">
    <h1>隋坡<span class="pin"> · </span>探店地图</h1>
    <p>B 站 UP 主「舌尖真探事务所 / 隋坡」探店店铺整理</p>
    <div class="stats" id="stats"></div>
  </div>
</header>

<div class="bar">
  <div class="wrap">
    <div class="controls">
      <input type="text" id="q" placeholder="搜索店名 / 标题 / 地点…">
      <select id="locsel"></select>
      <select id="sort">
        <option value="date">最新优先</option>
        <option value="play">最热优先</option>
        <option value="shop">按店名</option>
      </select>
      <button class="toggle on" id="tTandian" title="只看探店视频">仅探店</button>
      <button class="toggle amber" id="tReview" title="只看需人工补全的">待补全</button>
      <div class="seg" id="viewseg">
        <button class="on" id="vList">☰ 列表</button>
        <button id="vMap">📍 地图</button>
      </div>
      <span class="result-count" id="rc"></span>
    </div>
    <div class="locchart" id="locchart"></div>
  </div>
</div>

<div class="wrap">
  <div class="mapview" id="mapview" style="display:none">
    <div id="map"></div>
    <div id="mapfallback">地图组件加载失败（需联网加载 ECharts）。可继续使用列表视图。</div>
    <div class="mapbar">
      <div class="legend">
        <span>店铺数</span>
        <span class="ramp" id="rampleg"></span>
        <span>多</span>
      </div>
      <span class="hint">气泡大小=该城探店数；点击气泡可按城市筛选列表</span>
    </div>
  </div>

  <div class="grid" id="grid"></div>
  <div class="empty" id="empty" style="display:none">没有符合条件的记录</div>
  <footer id="foot"></footer>
</div>

<script>
const DATA = __DATA__;
const META = __META__;
const CHINA_GEO = __GEO__;
const CITY_COORDS = __COORDS__;
const PROV_FULL = __PROVFULL__;

const el = id => document.getElementById(id);
const fmtPlay = n => n>=10000 ? (n/10000).toFixed(1)+'万' : (n!=null?n:'-');
const esc = s => (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const needsReview = d => d.is_tandian && (!d.shop_name || !d.location || d.confidence!=='high');

const state = {q:'', loc:'__all', sort:'date', tandianOnly:true, reviewOnly:false, view:'list'};

/* ---- 顺序型暖色 ramp（light->dark） ---- */
const RAMP = ['#fbeae3','#f4c6b8','#ec8f7c','#d25543','#a8261a'];
function hex2rgb(h){h=h.replace('#','');return[parseInt(h.slice(0,2),16),parseInt(h.slice(2,4),16),parseInt(h.slice(4,6),16)];}
function mix(a,b,f){const A=hex2rgb(a),B=hex2rgb(b);return '#'+[0,1,2].map(i=>Math.round(A[i]+(B[i]-A[i])*f)).map(x=>x.toString(16).padStart(2,'0')).join('');}
function rampColor(t){t=Math.max(0,Math.min(1,t));const n=RAMP.length-1;const i=Math.min(n-1,Math.floor(t*n));const f=t*n-i;return mix(RAMP[i],RAMP[i+1],f);}

/* ---- 统计 ---- */
function uniqLocs(){
  const m={};
  DATA.filter(d=>d.is_tandian && d.location).forEach(d=>{m[d.location]=(m[d.location]||0)+1});
  return Object.entries(m).sort((a,b)=>b[1]-a[1]);
}
function renderStats(){
  const all=DATA.length, td=DATA.filter(d=>d.is_tandian).length;
  const locs=uniqLocs().length, rev=DATA.filter(needsReview).length;
  el('stats').innerHTML=`<div class="stat"><b>${all}</b>个视频</div>
    <div class="stat"><b>${td}</b>个探店</div><div class="stat"><b>${locs}</b>个城市</div>
    <div class="stat"><b>${rev}</b>项待人工补全</div>`;
  const u=uniqLocs(), max=u.length?u[0][1]:1;
  el('locchart').innerHTML=u.slice(0,12).map(([l,c])=>
    `<div class="locbar"><b>${esc(l)}</b><div class="track"><div class="fill" style="width:${c/max*100}%"></div></div><span>${c}</span></div>`).join('');
  el('rampleg').innerHTML=RAMP.map(c=>`<i style="background:${c}"></i>`).join('');
}
function renderLocSelect(){
  el('locsel').innerHTML=`<option value="__all">全部地点</option>`+
    uniqLocs().map(([l,c])=>`<option value="${esc(l)}">${esc(l)} (${c})</option>`).join('');
}

/* ---- 过滤 ---- */
function passes(d){
  if (state.tandianOnly && !d.is_tandian) return false;
  if (state.reviewOnly && !needsReview(d)) return false;
  if (state.loc!=='__all' && d.location!==state.loc) return false;
  const q=state.q.trim().toLowerCase();
  if (q){const hay=[d.shop_name,d.title,d.location,d.province].filter(Boolean).join(' ').toLowerCase();if(!hay.includes(q))return false;}
  return true;
}

/* ---- 卡片 ---- */
function cardHTML(d){
  const cover=d.cover?`<img loading="lazy" src="${esc(d.cover)}" alt="">`:'';
  const tag=d.is_tandian?`<span class="pill tandian">探店</span>`:`<span class="pill other">其它</span>`;
  const conf=`<span class="conf ${d.confidence||''}">${({high:'高',medium:'中',low:'低'})[d.confidence]||'-'}</span>`;
  const shop=d.is_tandian?(d.shop_name?`<div class="shop">${esc(d.shop_name)}</div>`:`<div class="shop missing">店名待补全</div>`)
    :`<div class="shop" style="color:var(--muted);font-size:14px">非探店视频</div>`;
  const loc=d.is_tandian&&d.location?`<span class="loc">📍 ${esc(d.location)}${d.province&&d.province!==d.location?' · '+esc(d.province):''}</span>`
    :(d.is_tandian?`<span class="loc unknown">📍 地点未知</span>`:'');
  const note=d.note?`<div class="note">⚠ ${esc(d.note)}</div>`:'';
  const play=d.play!=null?`<span class="plays">${fmtPlay(d.play)}</span>`:'';
  const date=d.pubdate?`<span>${esc(d.pubdate)}</span>`:'';
  return `<a class="card" href="${esc(d.url)}" target="_blank" rel="noopener">
    <div class="cover">${cover}${tag}${conf}</div><div class="body">${shop}
    <div class="vtitle" title="${esc(d.title)}">${esc(d.title)}</div>
    <div class="meta">${loc}${date}${play}</div>${note}
    <div class="foot"><span class="openlink">在 B 站查看</span></div></div></a>`;
}
function renderList(){
  let list=DATA.filter(passes);
  if(state.sort==='date')list.sort((a,b)=>(b.pubdate||'').localeCompare(a.pubdate||''));
  else if(state.sort==='play')list.sort((a,b)=>(b.play||0)-(a.play||0));
  else list.sort((a,b)=>(a.shop_name||'~').localeCompare(b.shop_name||'~','zh'));
  el('grid').innerHTML=list.map(cardHTML).join('');
  el('empty').style.display=list.length?'none':'block';
  el('rc').textContent=`共 ${list.length} 条`;
}

/* ---- 地图 ---- */
let mapChart=null, mapReady=false;
function ensureMap(){
  if(!window.echarts){ el('mapfallback').style.display='block'; el('map').style.display='none'; return null; }
  el('mapfallback').style.display='none'; el('map').style.display='block';
  if(!mapReady){ echarts.registerMap('china', CHINA_GEO); mapReady=true; }
  if(!mapChart){ mapChart=echarts.init(el('map')); window.addEventListener('resize',()=>mapChart&&mapChart.resize()); }
  return mapChart;
}
function aggForMap(){
  const byCoord={}, prov={};
  DATA.filter(passes).filter(d=>d.is_tandian).forEach(d=>{
    if(d.location && CITY_COORDS[d.location]){
      const c=CITY_COORDS[d.location], key=c[0].toFixed(1)+'_'+c[1].toFixed(1);
      (byCoord[key]=byCoord[key]||{coord:c,names:{},shops:[]}).shops.push(d);
      byCoord[key].names[d.location]=1;
    }
    if(d.province) prov[d.province]=(prov[d.province]||0)+1;
  });
  const points=Object.values(byCoord).map(p=>({
    value:[p.coord[0],p.coord[1],p.shops.length],
    names:Object.keys(p.names), shops:p.shops
  }));
  return {points, prov, maxProv:Math.max(1,...Object.values(prov)), maxCity:Math.max(1,...points.map(p=>p.value[2]))};
}
function renderMap(){
  const ch=ensureMap(); if(!ch) return;
  const {points,prov,maxProv,maxCity}=aggForMap();
  const regions=Object.keys(PROV_FULL).map(short=>({
    name:PROV_FULL[short],
    itemStyle:{ areaColor: prov[short] ? rampColor((prov[short]-1)/Math.max(1,maxProv-1)) : '#f3ece4' }
  }));
  ch.setOption({
    tooltip:{trigger:'item', backgroundColor:'rgba(43,38,34,.94)', borderColor:'transparent', textStyle:{color:'#fff',fontSize:12}},
    geo:{
      map:'china', roam:'move', zoom:1.18, center:[106,35],
      scaleLimit:{min:1, max:6},
      label:{show:false}, emphasis:{label:{show:true,color:'#222'}, itemStyle:{areaColor:null}},
      itemStyle:{areaColor:'#f3ece4', borderColor:'#d9cfc1', borderWidth:.6},
      regions: regions
    },
    series:[{
      type:'scatter', coordinateSystem:'geo', data:points,
      symbolSize:v=>14+Math.sqrt(v[2]/maxCity)*30,
      itemStyle:{color:'#c0392b', borderColor:'#fff', borderWidth:2, shadowBlur:6, shadowColor:'rgba(0,0,0,.25)'},
      emphasis:{scale:1.15, itemStyle:{color:'#a8261a'}},
      tooltip:{formatter:p=>{
        const list=p.data.shops.slice(0,8).map(s=>`<div style="opacity:.9">· ${esc(s.shop_name||'店名待补')}</div>`).join('');
        const more=p.data.shops.length>8?`<div style="opacity:.6;margin-top:2px">… 共 ${p.data.shops.length} 家</div>`:'';
        return `<div style="font-weight:700;margin-bottom:3px">${esc(p.data.names.join(' · '))} · ${p.data.value[2]} 家</div>${list}${more}`;
      }}
    }]
  }, true);
  ch.off('click'); ch.on('click',p=>{
    if(p.seriesType==='scatter' && p.data.names){
      const city=p.data.names[0];
      state.loc=city; el('locsel').value=city; switchView('list'); renderList();
    }
  });
}

/* ---- 视图切换 ---- */
function switchView(v){
  state.view=v;
  el('vList').classList.toggle('on', v==='list');
  el('vMap').classList.toggle('on', v==='map');
  el('mapview').style.display = v==='map' ? 'block':'none';
  el('grid').style.display = v==='map' ? 'none':'grid';
  el('empty').style.display = v==='map' ? 'none': (DATA.filter(passes).length?'none':'block');
  if(v==='map') renderMap();
}

/* ---- 绑定 ---- */
function bind(){
  el('q').addEventListener('input',e=>{state.q=e.target.value; state.view==='map'?renderMap():renderList();});
  el('locsel').addEventListener('change',e=>{state.loc=e.target.value; state.view==='map'?renderMap():renderList();});
  el('sort').addEventListener('change',e=>{state.sort=e.target.value; renderList();});
  el('tTandian').addEventListener('click',e=>{state.tandianOnly=!state.tandianOnly; e.target.classList.toggle('on',state.tandianOnly); state.view==='map'?renderMap():renderList();});
  el('tReview').addEventListener('click',e=>{state.reviewOnly=!state.reviewOnly; e.target.classList.toggle('on',state.reviewOnly); state.view==='map'?renderMap():renderList();});
  el('vList').addEventListener('click',()=>switchView('list'));
  el('vMap').addEventListener('click',()=>switchView('map'));
}

renderStats(); renderLocSelect(); bind(); renderList();
el('foot').innerHTML=`数据源：${esc(META.source)} · 共 ${DATA.length} 条 · 生成于 ${esc(META.generated)}<br>地图底图来自 DataV.GeoAtlas，仅用于位置示意。店铺信息以原视频为准。`;
</script>
</body>
</html>
"""

# 城市坐标表 [经度, 纬度]；按坐标合并可避免同点重叠（如"乌鲁木齐·新疆"）
CITY_COORDS = {
    "上海": [121.47, 31.23], "北京": [116.41, 39.90], "成都": [104.07, 30.57],
    "广州": [113.27, 23.13], "黄山": [118.34, 29.73], "重庆": [106.55, 29.56],
    "顺德": [113.25, 22.84], "河南": [113.65, 34.76], "无锡": [120.31, 31.49],
    "常德": [111.69, 29.04], "齐齐哈尔": [123.95, 47.35], "哈尔滨": [126.64, 45.75],
    "天津": [117.20, 39.13], "西安": [108.94, 34.34], "淮安": [119.02, 33.50],
    "太原": [112.55, 37.87], "南宁": [108.37, 22.82], "济南": [117.00, 36.65],
    "新疆": [87.62, 43.83], "乌鲁木齐": [87.62, 43.83], "山西": [112.55, 37.87],
    "湖南": [112.94, 28.23], "钦州": [108.62, 21.96], "沧州": [116.84, 38.31],
    "杭州": [120.16, 30.27], "洛阳": [112.45, 34.62], "西藏": [91.13, 29.65],
    "邯郸": [114.54, 36.62], "深圳": [114.06, 22.55], "泰安": [117.09, 36.19],
}

# 省份短名 -> GeoJSON 全称
PROV_FULL = {
    "北京": "北京市", "天津": "天津市", "上海": "上海市", "重庆": "重庆市",
    "河北": "河北省", "山西": "山西省", "辽宁": "辽宁省", "吉林": "吉林省",
    "黑龙江": "黑龙江省", "江苏": "江苏省", "浙江": "浙江省", "安徽": "安徽省",
    "福建": "福建省", "江西": "江西省", "山东": "山东省", "河南": "河南省",
    "湖北": "湖北省", "湖南": "湖南省", "广东": "广东省", "海南": "海南省",
    "四川": "四川省", "贵州": "贵州省", "云南": "云南省", "陕西": "陕西省",
    "甘肃": "甘肃省", "青海": "青海省", "台湾": "台湾省",
    "内蒙古": "内蒙古自治区", "广西": "广西壮族自治区", "西藏": "西藏自治区",
    "宁夏": "宁夏回族自治区", "新疆": "新疆维吾尔自治区",
    "香港": "香港特别行政区", "澳门": "澳门特别行政区",
}


def httpsify(url):
    if isinstance(url, str) and url.startswith("http://"):
        return "https://" + url[len("http://"):]
    return url


def main():
    data_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DATA
    with open(data_path, encoding="utf-8") as f:
        rows = json.load(f)
    for r in rows:
        r["cover"] = httpsify(r.get("cover"))
    with open(GEO_PATH, encoding="utf-8") as f:
        geo = json.load(f)
    meta = {
        "source": "Bilibili UID 3546888255048212（舌尖真探事务所 / 隋坡）",
        "generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "count": len(rows),
    }
    html = (
        HTML
        .replace("__DATA__", json.dumps(rows, ensure_ascii=False))
        .replace("__META__", json.dumps(meta, ensure_ascii=False))
        .replace("__GEO__", json.dumps(geo, ensure_ascii=False))
        .replace("__COORDS__", json.dumps(CITY_COORDS, ensure_ascii=False))
        .replace("__PROVFULL__", json.dumps(PROV_FULL, ensure_ascii=False))
    )
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"已生成 {OUT_HTML}（{len(rows)} 条，源 {data_path}，{len(html)//1024}KB）")


if __name__ == "__main__":
    main()
