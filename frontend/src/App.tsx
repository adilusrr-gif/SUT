import {useEffect,useMemo,useState,useRef} from 'react';
import {Economics,Setup} from './Economics';
import {Activity, BrainCircuit, Calculator, Database, Leaf, RefreshCw, Save, TrendingUp} from 'lucide-react';

type Group = {id:number;name:string;cow_count:number;body_weight_kg:number;milk_yield_l:number;target_dmi_kg:number;min_cp_pct:number;max_cp_pct:number;min_ndf_pct:number;max_ndf_pct:number;max_starch_pct:number;max_fat_pct:number;min_me_mcal_per_kg_dm:number;min_ca_pct:number;min_p_pct:number;transition_limit_pct:number;farm_id:number};
type Feed = {id:number;name:string;dm_pct:number;cp_pct:number;ndf_pct:number;starch_pct:number;fat_pct:number;me_mcal_per_kg_dm:number;ca_pct:number;p_pct:number;price_kzt_per_kg:number;min_as_fed_kg:number;max_as_fed_kg:number;active:boolean};
let accessToken = '';
export const api=async(path:string,init?:RequestInit)=>{
 const headers=new Headers(init?.headers);headers.set('Content-Type','application/json');headers.set('Authorization','Bearer '+accessToken);
 const r=await fetch(path,{...init,headers});
 if(!r.ok){const body=await r.json().catch(()=>null);const error:any=new Error(r.status===401?'Код доступа неверен. Войдите повторно.':typeof body?.detail==='string'?body.detail:`Не удалось выполнить запрос (${r.status}). Проверьте данные.`);error.status=r.status;throw error}
 return r.status===204?null:r.json();
};
export default function App(){
 const [ready,setReady]=useState(false),[token,setToken]=useState(''),[error,setError]=useState(''),[loading,setLoading]=useState(false);
 const login=async(e:React.FormEvent)=>{e.preventDefault();setLoading(true);setError('');accessToken=token;try{await api('/api/ai/status');setToken('');setReady(true)}catch(e:any){accessToken='';setError(e.message)}finally{setLoading(false)}};
 if(ready)return <><button className="logout" onClick={()=>{accessToken='';setReady(false)}}>Выйти</button><Workspace/></>;
 return <main className="login"><section><h1>Süt • Рацион</h1><p>Введите код доступа фермы. Ключ OpenAI вводится только на сервере.</p><form onSubmit={login}><label>Код доступа<input type="password" autoComplete="current-password" value={token} onChange={e=>setToken(e.target.value)} required/></label><button className="primary" disabled={loading}>{loading?'Проверяем…':'Войти'}</button></form>{error&&<p role="alert">{error}</p>}</section></main>;
}
const money=(v:number)=>new Intl.NumberFormat('ru-RU',{maximumFractionDigits:0}).format(v||0)+' ₸';

function Workspace(){
 const [tab,setTab]=useState('dashboard'),[groups,setGroups]=useState<Group[]>([]),[feeds,setFeeds]=useState<Feed[]>([]),[gid,setGid]=useState<number>(1),[dashboard,setDashboard]=useState<any>(null),[ration,setRation]=useState<any[]>([]),[opt,setOpt]=useState<any>(null),[ai,setAi]=useState(''),[busy,setBusy]=useState(false),[err,setErr]=useState(''),[initialized,setInitialized]=useState(false);
 const group=groups.find(g=>g.id===gid);
 const requestVersion=useRef(0);
 const loadData=async(id:number,version:number)=>{
  const [d,r]=await Promise.all([api('/api/dashboard/'+id),api('/api/ration/'+id)]);
  if(version!==requestVersion.current)return;
  setDashboard(d);setRation(r);setOpt(d.latest_optimization);setAi('');
 };
 const load=async()=>{const version=++requestVersion.current;setErr('');setDashboard(null);setRation([]);setOpt(null);try{
  const [g,f]=await Promise.all([api('/api/groups'),api('/api/feeds')]);
  if(version!==requestVersion.current)return;
  setGroups(g);setFeeds(f);setInitialized(true);const id=g.some((x:Group)=>x.id===gid)?gid:g[0]?.id;
  if(!id)return;
  if(id!==gid){setGid(id);return}await loadData(id,version);
 }catch(e:any){if(version===requestVersion.current)setErr(e.message)}};
 useEffect(()=>{load();return()=>{requestVersion.current++}},[]);
 useEffect(()=>{if(groups.length)loadGroup()},[gid]);
 const loadGroup=async()=>{const version=++requestVersion.current;setDashboard(null);setRation([]);setOpt(null);setAi('');setErr('');try{await loadData(gid,version)}catch(e:any){if(version===requestVersion.current)setErr(e.message)}};
 const optimize=async()=>{const version=requestVersion.current;setBusy(true);setErr('');try{const o=await api('/api/optimize/'+gid,{method:'POST'});const d=await api('/api/dashboard/'+gid);if(version===requestVersion.current){setOpt(o);setDashboard(d);setAi('')}}catch(e:any){setErr(e.message)}finally{setBusy(false)}};
 const explain=async()=>{if(!opt?.id)return;const version=requestVersion.current;setBusy(true);try{const x=await api('/api/ai/explain/'+opt.id,{method:'POST'});if(version===requestVersion.current)setAi(x.text+'\n\n'+(x.cached?'Сохранённое пояснение — без нового вызова модели.':x.source==='llm_constrained'?'Пояснение: '+x.provider+' / '+x.model:'Шаблонное пояснение: '+(x.reason==='daily_limit'?'достигнут дневной лимит.':'модель недоступна или не настроена.')))}catch(e:any){setErr(e.message)}finally{setBusy(false)}};
 return <div className="app"><aside><div className="brand"><div className="logo"><Leaf size={22}/></div><div><b>Süt</b><span>Рацион • v2.3</span></div></div><nav>{[['dashboard','Обзор',Activity],['data','Данные',Database],['optimizer','Оптимизация',Calculator],['ai','ИИ-пояснение',BrainCircuit]].map(([k,l,I]:any)=><button className={tab===k?'active':''} onClick={()=>setTab(k)} key={k}><I size={18}/>{l}</button>)}</nav><div className="sideFoot">LP считает. ИИ объясняет.<br/>Решение подтверждает зоотехник.</div></aside>
 <main><header><div><h1>{tab==='dashboard'?'Экономика кормления':tab==='data'?'Ручной ввод данных':tab==='optimizer'?'Оптимизация рациона':'ИИ • пояснение'}</h1><p>Ферма: {dashboard?.farm?.name||'—'}</p></div><div className="toolbar"><select disabled={busy} value={gid} onChange={e=>setGid(+e.target.value)}>{groups.map(g=><option key={g.id} value={g.id}>{g.name}</option>)}</select><button className="ghost" onClick={load}><RefreshCw size={16}/></button></div></header>
 {err&&<div className="error">{err}</div>}
 {initialized&&!groups.length&&<Setup onDone={load}/>}
 {tab==='dashboard'&&group&&dashboard?.group?.id===gid&&<Economics key={gid} group={group}/>}
 {tab==='dashboard'&&dashboard&&<Dashboard d={dashboard} opt={opt} onOptimize={optimize} busy={busy}/>} 
 {tab==='data'&&group&&dashboard?.group?.id===gid&&<DataEditor key={gid} group={group} farm={dashboard?.farm} feeds={feeds} ration={ration} onReload={load}/>} 
 {tab==='optimizer'&&group&&<Optimizer group={group} feeds={feeds} ration={ration} opt={opt} onOptimize={optimize} busy={busy}/>} 
 {tab==='ai'&&<AI opt={opt} ai={ai} explain={explain} busy={busy}/>} 
 </main></div>
}

function Dashboard({d,opt,onOptimize,busy}:any){const c=d.current;return <><div className="hero"><div><span className="eyebrow">Деньги фермы</span><h2>{d.group.name} · {d.group.cow_count} голов</h2><p>{d.note}</p></div><button className="primary" onClick={onOptimize} disabled={busy}><TrendingUp size={18}/>{busy?'Считаю...':'Оптимизировать рацион'}</button></div><div className="cards"><Card title="Корм / корова / день" value={money(c.feed_cost_per_cow_day_kzt)} sub="расчёт по текущим ценам"/><Card title="Выручка молока / день" value={money(c.milk_revenue_per_cow_day_kzt)} sub="расчёт по заданному удою"/><Card title="Маржа над кормом" value={money(c.margin_over_feed_per_cow_day_kzt)} sub="не чистая прибыль"/><Card title="Корм / группа / месяц" value={money(c.feed_cost_group_month_kzt)} sub="проекция на 30 дней"/></div>{opt&&<section><div className="sectionTitle"><div><span className="eyebrow">Последний расчёт</span><h3>Потенциал экономии</h3></div></div><div className="savings"><div><span>На корову / день</span><strong>{money(opt.savings_per_cow_day_kzt)}</strong></div><div><span>На группу / месяц</span><strong>{money(opt.savings_group_month_kzt)}</strong></div><div><span>Корм было → стало</span><strong>{money(opt.before_cost_kzt)} → {money(opt.after_cost_kzt)}</strong></div></div></section>}</>}
function Card({title,value,sub}:any){return <div className="card"><span>{title}</span><strong>{value}</strong><small>{sub}</small></div>}

function DataEditor({group,farm,feeds,ration,onReload}:any){
 const [f,setF]=useState(farm||{name:'',herd_size:1,milk_price_kzt:220});
 const [g,setG]=useState(group); const [r,setR]=useState<Record<number,number>>({}); const [feedRows,setFeedRows]=useState<any[]>(feeds);
 const [obs,setObs]=useState({group_id:group.id,observed_on:new Date().toISOString().slice(0,10),milk_yield_l:group.milk_yield_l,fat_pct:3.7,protein_pct:3.2,somatic_cells_k:160,note:''});
 const [newFeed,setNewFeed]=useState({name:'',dm_pct:88,cp_pct:12,ndf_pct:35,starch_pct:10,fat_pct:3,me_mcal_per_kg_dm:2.3,ca_pct:.5,p_pct:.3,price_kzt_per_kg:100,min_as_fed_kg:0,max_as_fed_kg:20,active:true});
 const [saveError,setSaveError]=useState(''),[saving,setSaving]=useState(false),[saved,setSaved]=useState(false);
 const save=async(action:()=>Promise<void>)=>{if(saving)return;setSaving(true);setSaveError('');setSaved(false);try{await action();setSaved(true)}catch(e:any){setSaveError(e.message)}finally{setSaving(false)}};
 useEffect(()=>{setG(group);setObs((x:any)=>({...x,group_id:group.id,milk_yield_l:group.milk_yield_l}))},[group]);
 useEffect(()=>{if(farm)setF(farm)},[farm]); useEffect(()=>setFeedRows(feeds),[feeds]);
 useEffect(()=>{const x:any={};ration.forEach((z:any)=>x[z.feed_id]=z.kg_as_fed);setR(x)},[ration]);
 const saveFarm=async()=>{await api('/api/farm',{method:'PUT',body:JSON.stringify({name:f.name,herd_size:+f.herd_size,milk_price_kzt:+f.milk_price_kzt})});await onReload()};
 const saveGroup=async()=>{await api('/api/groups/'+group.id,{method:'PUT',body:JSON.stringify(g)});await onReload()};
 const saveRation=async()=>{await api('/api/ration/'+group.id,{method:'PUT',body:JSON.stringify({lines:feeds.map((x:any)=>({feed_id:x.id,kg_as_fed:+(r[x.id]||0)}))})});await onReload()};
 const saveFeed=async(row:any)=>{await api('/api/feeds/'+row.id,{method:'PUT',body:JSON.stringify(row)});await onReload()};
 const addFeed=async()=>{await api('/api/feeds',{method:'POST',body:JSON.stringify(newFeed)});setNewFeed({...newFeed,name:''});await onReload()};
 const addObs=async()=>{await api('/api/observations',{method:'POST',body:JSON.stringify(obs)});await onReload()};
 const updFeed=(id:number,k:string,v:any)=>setFeedRows((rows:any[])=>rows.map(x=>x.id===id?{...x,[k]:v}:x));
 return <>
  {saveError&&<p className="error" role="alert">{saveError}</p>}{saved&&<p role="status">Сохранено</p>}
  <section><h3>Ферма</h3><div className="gridForm"><Txt label="Название фермы" k="name" o={f} s={setF}/><Num label="Поголовье" k="herd_size" o={f} s={setF}/><Num label="Цена молока, ₸/л" k="milk_price_kzt" o={f} s={setF}/></div><button className="secondary" disabled={saving} onClick={()=>save(saveFarm)}><Save size={16}/>Сохранить ферму</button></section>
  <section><h3>Группа и целевые ограничения</h3><div className="gridForm"><Txt label="Название группы" k="name" o={g} s={setG}/><Num label="Коров" k="cow_count" o={g} s={setG}/><Num label="Масса, кг" k="body_weight_kg" o={g} s={setG}/><Num label="Удой, л" k="milk_yield_l" o={g} s={setG}/><Num label="DMI цель, кг СВ" k="target_dmi_kg" o={g} s={setG}/><Num label="CP min, % СВ" k="min_cp_pct" o={g} s={setG}/><Num label="CP max, % СВ" k="max_cp_pct" o={g} s={setG}/><Num label="NDF min, % СВ" k="min_ndf_pct" o={g} s={setG}/><Num label="NDF max, % СВ" k="max_ndf_pct" o={g} s={setG}/><Num label="Крахмал max, %" k="max_starch_pct" o={g} s={setG}/><Num label="Жир max, %" k="max_fat_pct" o={g} s={setG}/><Num label="ME min, Mcal/кг СВ" k="min_me_mcal_per_kg_dm" o={g} s={setG}/><Num label="Ca min, % СВ" k="min_ca_pct" o={g} s={setG}/><Num label="P min, % СВ" k="min_p_pct" o={g} s={setG}/><Num label="Переход max, %" k="transition_limit_pct" o={g} s={setG}/></div><button className="secondary" disabled={saving} onClick={()=>save(saveGroup)}><Save size={16}/>Сохранить группу</button></section>
  <section><h3>Корма — состав, цена и границы</h3><div className="wideTable"><div className="feedEdit head"><span>Корм</span><span>₸/кг</span><span>СВ%</span><span>CP%</span><span>NDF%</span><span>Крах%</span><span>Жир%</span><span>ME</span><span>Ca%</span><span>P%</span><span>min кг</span><span>max кг</span><span></span></div>{feedRows.map((x:any)=><div className="feedEdit" key={x.id}><input value={x.name} onChange={e=>updFeed(x.id,'name',e.target.value)}/>{['price_kzt_per_kg','dm_pct','cp_pct','ndf_pct','starch_pct','fat_pct','me_mcal_per_kg_dm','ca_pct','p_pct','min_as_fed_kg','max_as_fed_kg'].map(k=><input key={k} type="number" step="0.01" value={x[k]} onChange={e=>updFeed(x.id,k,+e.target.value)}/>)}<button className="mini" disabled={saving} onClick={()=>save(()=>saveFeed(x))}>OK</button></div>)}</div></section>
  <section><h3>Текущий рацион — кг на корову в день</h3><div className="feedTable"><div className="tr th"><span>Корм</span><span>Цена ₸/кг</span><span>СВ %</span><span>кг/кор/день</span></div>{feeds.map((x:any)=><div className="tr" key={x.id}><span>{x.name}</span><span>{x.price_kzt_per_kg}</span><span>{x.dm_pct}</span><input type="number" step="0.1" value={r[x.id]??0} onChange={e=>setR({...r,[x.id]:+e.target.value})}/></div>)}</div><button className="secondary" disabled={saving} onClick={()=>save(saveRation)}><Save size={16}/>Сохранить рацион</button></section>
  <section><h3>Наблюдение по молоку — ручной контроль «до/после»</h3><div className="gridForm"><label><span>Дата</span><input type="date" value={obs.observed_on} onChange={e=>setObs({...obs,observed_on:e.target.value})}/></label><Num label="Удой, л" k="milk_yield_l" o={obs} s={setObs}/><Num label="Жир, %" k="fat_pct" o={obs} s={setObs}/><Num label="Белок, %" k="protein_pct" o={obs} s={setObs}/><Num label="Соматика, тыс." k="somatic_cells_k" o={obs} s={setObs}/><Txt label="Комментарий" k="note" o={obs} s={setObs}/></div><button className="secondary" disabled={saving} onClick={()=>save(addObs)}><Save size={16}/>Записать наблюдение</button></section>
  <section><h3>Добавить новый корм</h3><div className="gridForm"><Txt label="Название" k="name" o={newFeed} s={setNewFeed}/><Num label="Цена ₸/кг" k="price_kzt_per_kg" o={newFeed} s={setNewFeed}/><Num label="СВ %" k="dm_pct" o={newFeed} s={setNewFeed}/><Num label="CP % СВ" k="cp_pct" o={newFeed} s={setNewFeed}/><Num label="NDF % СВ" k="ndf_pct" o={newFeed} s={setNewFeed}/><Num label="Крахмал % СВ" k="starch_pct" o={newFeed} s={setNewFeed}/><Num label="Жир % СВ" k="fat_pct" o={newFeed} s={setNewFeed}/><Num label="ME Mcal/кг СВ" k="me_mcal_per_kg_dm" o={newFeed} s={setNewFeed}/><Num label="Ca % СВ" k="ca_pct" o={newFeed} s={setNewFeed}/><Num label="P % СВ" k="p_pct" o={newFeed} s={setNewFeed}/><Num label="min кг" k="min_as_fed_kg" o={newFeed} s={setNewFeed}/><Num label="max кг" k="max_as_fed_kg" o={newFeed} s={setNewFeed}/></div><button className="secondary" disabled={saving||!newFeed.name} onClick={()=>save(addFeed)}>Добавить корм</button></section>
 </>}
function Num({label,k,o,s}:any){return <label><span>{label}</span><input type="number" step="0.01" value={o[k]??''} onChange={e=>s({...o,[k]:+e.target.value})}/></label>}function Txt({label,k,o,s}:any){return <label><span>{label}</span><input value={o[k]??''} onChange={e=>s({...o,[k]:e.target.value})}/></label>}

function Optimizer({group,feeds,ration,opt,onOptimize,busy}:any){const names=useMemo(()=>Object.fromEntries(feeds.map((f:any)=>[f.id,f.name])),[feeds]);return <><div className="hero"><div><span className="eyebrow">LP / линейное программирование</span><h2>Минимальная стоимость при заданных ограничениях</h2><p>Считает по сухому веществу, CP, NDF, крахмалу, жиру, ME, Ca, P и ограничению плавного перехода.</p></div><button className="primary" onClick={onOptimize} disabled={busy}><Calculator size={18}/>{busy?'Расчёт...':'Рассчитать'}</button></div>{opt&&<section><h3>Предложение</h3><div className="feedTable"><div className="tr th"><span>Корм</span><span>Было</span><span>Стало</span><span>Δ кг</span></div>{Object.keys(opt.proposed_json||{}).map((id:string)=>{const a=+(opt.before_json?.[id]||0),b=+(opt.proposed_json?.[id]||0);return <div className="tr" key={id}><span>{opt.feeds?.[id]||names[+id]||id}</span><span>{a.toFixed(2)}</span><span>{b.toFixed(2)}</span><span className={b-a<0?'down':'up'}>{(b-a).toFixed(2)}</span></div>})}</div><div className="nutrients">{Object.entries(opt.nutrients_json||{}).map(([k,v]:any)=><div key={k}><span>{k}</span><b>{v}</b></div>)}</div><div className="warnings">{(opt.warnings_json||[]).map((x:string,i:number)=><p key={i}>• {x}</p>)}</div></section>}</>}

function AI({opt,ai,explain,busy}:any){
 const [status,setStatus]=useState<any>(null);
 useEffect(()=>{api('/api/ai/status').then(setStatus).catch(()=>setStatus(null))},[ai]);
 return <><div className="hero"><div><span className="eyebrow">OpenAI / Ollama</span><h2>ИИ не решает — только объясняет</h2><p>Модель выбирает акцент пояснения. Все числа подставляются из расчёта. При недоступности ИИ или исчерпании дневного лимита работает шаблонное пояснение.</p></div><button className="primary" disabled={!opt||busy} onClick={explain}><BrainCircuit size={18}/>{busy?'Генерация...':'Объяснить расчёт'}</button></div><section>{status&&<p>Провайдер: {status.provider} · Модель: {status.model||"отключена"} · Настройки: {status.configured?"заданы (связь не проверялась)":"не заданы"} · Вызовы сегодня: {status.calls_today}/{status.daily_call_limit}</p>}<h3>Текст для фермера</h3><pre className="aiBox">{ai||'Сначала выполните оптимизацию, затем нажмите «Объяснить расчёт».'}</pre></section></>}
