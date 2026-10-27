/* Alleen lopende formulieren; geen casusopslag, cookies of externe verzoeken. */
(() => {
 const boxes=[...document.querySelectorAll('input[form="pilot-vergelijk"][name="ids"]')];
 const button=document.getElementById('pilot-knop');
 const selected=()=>boxes.filter(x=>x.checked);
 const update=()=>{const chosen=selected(),n=chosen.length;const bar=document.getElementById('pilot-vergelijk');if(bar)bar.hidden=n===0;if(button)button.disabled=n<2||n>3;const t=document.getElementById('pilot-teller');if(t)t.textContent=n===0?'Selecteer twee of drie aanbieders.':n===1?'1 geselecteerd — kies nog één aanbieder.':n+' geselecteerd — klaar om te vergelijken.';const names=document.getElementById('pilot-selectienamen');if(names)names.textContent=chosen.map(x=>x.dataset.naam||x.value).join(' · ');};
 boxes.forEach(x=>x.addEventListener('change',()=>{const error=document.getElementById('pilot-selectiefout');if(selected().length>3){x.checked=false;if(error)error.textContent='U kunt maximaal drie aanbieders vergelijken. Verwijder eerst een selectie.';}else if(error)error.textContent='';update();}));update();
 document.querySelectorAll('form').forEach(form=>form.addEventListener('submit',()=>{
  if(form.id==='pilot-vergelijk'||form.dataset.resetSelectie==='1')return;
  const ids=selected().map(x=>x.value);form.querySelectorAll('input[type="hidden"][name="ids"]').forEach(x=>x.remove());ids.forEach(value=>{const x=document.createElement('input');x.type='hidden';x.name='ids';x.value=value;form.appendChild(x);});
 }));
 const differences=document.getElementById('z-verschillen');
 if(differences)differences.addEventListener('change',()=>{
  document.querySelectorAll('[data-vergelijkrij],[data-vergelijkgroep]').forEach(row=>{
   const cells=[...row.querySelectorAll('td,.z-mobile-cell>div')].map(e=>e.textContent.replace(/\s+/g,' ').trim());
   row.hidden=differences.checked&&row.dataset.waarschuwing!=='1'&&new Set(cells).size===1;
  });
 });
 const errors=document.getElementById('foutoverzicht');if(errors)errors.focus();
})();
