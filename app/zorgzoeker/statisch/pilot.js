(() => {
 const boxes=[...document.querySelectorAll('input[form="pilot-vergelijk"][name="ids"]')];
 const button=document.getElementById('pilot-knop');
 const update=()=>{const n=boxes.filter(x=>x.checked).length; if(button)button.disabled=n<2||n>3;const t=document.getElementById('pilot-teller');if(t)t.textContent=n+' geselecteerd (twee of drie nodig)';};
 boxes.forEach(x=>x.addEventListener('change',()=>{if(boxes.filter(b=>b.checked).length>3)x.checked=false;update();}));update();
})();
// Alleen de lopende formulieren; geen localStorage, sessie of casusopslag.
document.querySelectorAll('form').forEach(form=>form.addEventListener('submit',()=>{
 if(form.id==='pilot-vergelijk')return;
 const selected=[...document.querySelectorAll('input[form="pilot-vergelijk"][name="ids"]:checked')].map(x=>x.value);
 form.querySelectorAll('input[type="hidden"][name="ids"]').forEach(x=>x.remove());
 selected.forEach(value=>{const x=document.createElement('input');x.type='hidden';x.name='ids';x.value=value;form.appendChild(x);});
}));
