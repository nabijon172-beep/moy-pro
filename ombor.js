(()=>{
const nav=document.querySelector('nav'),main=document.querySelector('main');
let tovarlar=[],sarf=[];
document.head.insertAdjacentHTML('beforeend','<style>select{width:100%;min-width:0;font:inherit;padding:12px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink)}nav button{font-size:.78rem}#sf-list a{color:var(--oil)}@media(min-width:800px){nav button{font-size:1rem}}</style>');
nav.insertAdjacentHTML('beforeend','<button data-t="om" class="ega">Ombor</button>');
main.insertAdjacentHTML('beforeend',`
<section id="s-om"><div class="card"><h2>Ombor</h2><div id="om-list"></div></div>
<div class="card"><h2>Yangi tovar</h2><p style="margin-top:0"><small>Moy, filtr, antifriz, svecha, tormoz kolodkasi va h.k. — istalgan turdagi mahsulot.</small></p><div class="two"><input id="t-nom" placeholder="Nomi: Shell 5W-30 yoki Antifriz G12"><input id="t-bir" placeholder="Birlik: litr, dona, kg"></div><button id="t-qosh" style="margin-top:8px">Tovar qo'shish</button></div>
<div class="card"><h2>Tovar kirimi</h2><div class="f"><select id="k-tovar"></select><div class="two"><input id="k-miq" type="number" step="any" placeholder="Miqdor"><input id="k-narx" type="number" step="any" placeholder="Birlik narxi, so'm"></div><button id="k-saqla">Kirim qilish</button></div></div></section>
<section id="s-pr"><div class="card"><h2>Parolni almashtirish</h2><div class="f"><input id="pr-eski" type="password" placeholder="Eski parol" autocomplete="current-password"><input id="pr-yangi" type="password" placeholder="Yangi parol (6+ belgi)" autocomplete="new-password"><button id="pr-saqla">Saqlash</button></div></div></section>`);
$('#f-saqla').insertAdjacentHTML('beforebegin',`<div id="sarf-box"><small>Ombordan sarflangan tovar (ixtiyoriy)</small><div class="two" style="margin:6px 0"><select id="sf-tovar"></select><input id="sf-miq" type="number" step="any" placeholder="Miqdor"></div><button class="sec" id="sf-qosh" style="width:100%">Tovarni qo'shish</button><div id="sf-list"></div></div>`);
$('#f-saqla').insertAdjacentHTML('afterend','<div id="chek-link"></div>');
$('#chiq').insertAdjacentHTML('beforebegin','<button class="sec" id="pr-tugma" style="padding:6px 10px">Parol</button>');

async function tovarYukla(){
  tovarlar=await api('tovar');
  const opt=tovarlar.map(t=>`<option value="${t.id}">${esc(t.nom)} (${+t.qoldiq.toFixed(2)} ${esc(t.birlik)})</option>`).join('')||'<option value="">Ombor bo\'sh</option>';
  ['#sf-tovar','#k-tovar'].forEach(s=>$(s).innerHTML=opt);
  $('#om-list').innerHTML=tovarlar.length?tovarlar.map(t=>`<div class="tr"><span>${esc(t.nom)}</span><span style="display:flex;align-items:center;gap:12px"><b class="oil">${+t.qoldiq.toFixed(2)} ${esc(t.birlik)}, ${pul(t.tannarx)} / ${esc(t.birlik)}</b><a href="#" data-e="${t.id}">Tahrirlash</a><a href="#" data-o="${t.id}" style="color:#e5484d">O'chirish</a></span></div>`).join(''):'<div class="empty">Ombor bo\'sh. Pastdan tovar qo\'shing (moy, antifriz, svecha, tormoz kolodkasi va h.k.).</div>'}
function sarfChiz(){$('#sf-list').innerHTML=sarf.map((s,i)=>`<div class="tr"><span>${esc(s.nom)}: ${s.miqdor} ${esc(s.birlik)}</span><a href="#" data-x="${i}">O'chirish</a></div>`).join('')}

$('#om-list').onclick=e=>{
  const eid=e.target.dataset.e,oid=e.target.dataset.o;
  if(!eid&&!oid)return;
  e.preventDefault();
  const t=tovarlar.find(x=>x.id==(eid||oid));
  if(eid)return act(async()=>{
    const nom=prompt('Tovar nomi:',t.nom);if(nom===null)return;
    const birlik=prompt("Birlik (litr, dona, kg va h.k.):",t.birlik);if(birlik===null)return;
    const qoldiq=prompt('Qoldiq miqdori:',t.qoldiq);if(qoldiq===null||isNaN(+qoldiq))return;
    const tannarx=prompt("Bir birlik narxi, so'm:",t.tannarx);if(tannarx===null||isNaN(+tannarx))return;
    await api('tovar/tahrirla',{id:t.id,nom,birlik,qoldiq:+qoldiq,tannarx:+tannarx});
    toast('Tovar yangilandi');await tovarYukla()});
  if(!confirm(`"${t.nom}" butunlay o'chirilsinmi?`))return;
  act(async()=>{await api('tovar/ochir',{id:t.id});toast('Tovar o\'chirildi');await tovarYukla()})};

$('#sf-qosh').onclick=()=>act(async()=>{
  const id=+$('#sf-tovar').value,m=+$('#sf-miq').value,t=tovarlar.find(x=>x.id==id);
  if(!t||!(m>0))throw 'Tovarni tanlang va miqdorini kiriting';
  sarf.push({tovar_id:id,miqdor:m,nom:t.nom,birlik:t.birlik});$('#sf-miq').value='';sarfChiz()});
$('#sf-list').onclick=e=>{const i=e.target.dataset.x;if(i!==undefined){e.preventDefault();sarf.splice(+i,1);sarfChiz()}};

$('#f-saqla').onclick=()=>act(async()=>{
  const j=await api('xizmat2',{raqam:$('#f-raqam').value,rusum:$('#f-rusum').value,ism:$('#f-ism').value,telefon:$('#f-tel').value,km:+$('#f-km').value,moy:$('#f-moy').value,filtr:$('#f-filtr').checked,summa:+$('#f-sum').value,sarflar:sarf.map(s=>({tovar_id:s.tovar_id,miqdor:s.miqdor}))});
  ['#f-raqam','#f-rusum','#f-ism','#f-tel','#f-km','#f-sum','#f-moy'].forEach(s=>$(s).value='');$('#f-filtr').checked=false;sarf=[];sarfChiz();
  toast('Saqlandi. Keyingi almashtirish: '+j.keyingi_km+' km yoki '+j.keyingi_sana);
  $('#chek-link').innerHTML=`<a class="btn sec" style="display:block" href="/chek/${j.id}" target="_blank">Chek chiqarish</a>`;
  await yangila()});

$('#t-qosh').onclick=()=>act(async()=>{await api('tovar',{nom:$('#t-nom').value,birlik:$('#t-bir').value});$('#t-nom').value='';$('#t-bir').value='';toast('Tovar qo\'shildi');await tovarYukla()});
$('#k-saqla').onclick=()=>act(async()=>{await api('kirim',{tovar_id:+$('#k-tovar').value,miqdor:+$('#k-miq').value,narx:+$('#k-narx').value});$('#k-miq').value='';$('#k-narx').value='';toast('Kirim saqlandi');await tovarYukla()});
$('#pr-tugma').onclick=()=>{document.querySelectorAll('nav button,section').forEach(x=>x.classList.remove('on'));$('#s-pr').classList.add('on')};
$('#pr-saqla').onclick=()=>act(async()=>{await api('parol',{eski:$('#pr-eski').value,yangi:$('#pr-yangi').value});$('#pr-eski').value='';$('#pr-yangi').value='';toast('Parol almashtirildi')});

const _y=yangila;yangila=async()=>{await _y();await tovarYukla()};
const _h=hisobot;hisobot=async()=>{await _h();const f=await api('foyda');
  $('#hs').insertAdjacentHTML('afterbegin',`<div class="grid" style="margin-bottom:12px"><div class="card"><small>Bugungi foyda</small><div class="n oil">${pul(f.bugun.foyda)}</div><small>Xarajat: ${pul(f.bugun.xarajat)}</small></div><div class="card"><small>Oylik foyda</small><div class="n">${pul(f.oy.foyda)}</div><small>Xarajat: ${pul(f.oy.xarajat)}</small></div></div>`)};
act(tovarYukla);
})();