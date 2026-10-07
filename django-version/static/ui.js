'use strict';
const MesaUI = (() => {
  const paths={home:'M3 10 12 3l9 7M5 9v11h5v-6h4v6h5V9',orders:'M8 5h12v16H4V5h4M8 3h8v4H8zM8 12h8M8 16h5',assets:'M4 4h16v16H4zM8 8h8v8H8zM2 8h2M2 16h2M20 8h2M20 16h2',inventory:'m3 7 9-4 9 4v10l-9 4-9-4zM3 7l9 4 9-4M12 11v10M7 5l9 4',calendar:'M5 5h14v16H5zM8 3v4M16 3v4M5 10h14M8 14h2M14 14h2M8 17h2',users:'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M18 4a4 4 0 0 1 0 7M18 15a4 4 0 0 1 4 4v2',bell:'M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4',menu:'M4 6h16M4 12h16M4 18h16',logout:'M9 4H4v16h5M8 12h13M16 7l5 5-5 5',plus:'M12 4v16M4 12h16',clock:'M12 8v5l3 2M22 12a10 10 0 1 0-20 0 10 10 0 0 0 20 0',money:'M12 2v20M17 6H9a4 4 0 0 0 0 8h6a4 4 0 0 0 0-8',sun:'M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.41M17.66 6.34l1.41-1.41M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0',moon:'M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79',close:'m6 6 12 12M6 18 18 6'};
  const icon=name=>`<svg class="icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="${paths[name]||paths.orders}"/></svg>`;
  let sequence=0;
  function decorate(root){
    root.querySelectorAll('.metric-icon:not([data-svg]),.asset-symbol:not([data-svg])').forEach(el=>{
      const key={'≡':'orders','●':'bell','◴':'clock','$':'money','＋':'plus','◇':'assets'}[el.textContent.trim()]||'orders';
      el.dataset.svg='true';el.innerHTML=icon(key);
    });
    root.querySelectorAll('.field').forEach(field=>{
      const label=field.querySelector('label'),input=field.querySelector('input:not([type=hidden]),select,textarea');
      if(label&&input&&!label.htmlFor&&!label.contains(input)){input.id ||= `field-${++sequence}`;label.htmlFor=input.id;}
    });
    root.querySelectorAll('.search').forEach(input=>input.setAttribute('aria-label',input.placeholder||'Buscar'));
    root.querySelectorAll('.material-row').forEach(row=>{
      row.querySelectorAll('[data-material]').forEach(input=>input.setAttribute('aria-label',({code:'Código del material',description:'Material',quantity:'Cantidad',unit_cost:'Costo unitario'})[input.dataset.material]));
      row.querySelector('.remove-material')?.setAttribute('aria-label','Quitar material');
    });
    root.querySelectorAll('.table-wrap').forEach(wrap=>{
      if(wrap.querySelector('th')?.textContent==='Folio'&&wrap.querySelectorAll('thead th').length===6)wrap.classList.add('orders-responsive');
      wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-label','Listado; desplaza horizontalmente para consultar todas las columnas');
    });
    root.querySelectorAll('.filter-chip').forEach(b=>b.setAttribute('aria-pressed',String(b.classList.contains('active'))));
  }
  function dialog(wrap){
    const previous=document.activeElement,modal=wrap.querySelector('.modal');
    modal.setAttribute('role','dialog');modal.setAttribute('aria-modal','true');
    const title=wrap.querySelector('h2');title.id=`dialog-${++sequence}`;modal.setAttribute('aria-labelledby',title.id);
    wrap.querySelector('.close')?.setAttribute('aria-label','Cerrar diálogo');
    const shell=document.querySelector('.app-shell');shell.inert=true;const oldOverflow=document.body.style.overflow;document.body.style.overflow='hidden';
    const close=()=>{wrap.remove();shell.inert=!document.querySelector('#login-screen').classList.contains('hidden');document.body.style.overflow=oldOverflow;if(previous?.isConnected)previous.focus();};
    wrap.addEventListener('keydown',e=>{
      if(e.key==='Escape'){e.preventDefault();close();return;}
      if(e.key!=='Tab')return;
      const focusable=[...wrap.querySelectorAll('button,input:not([type=hidden]),select,textarea,a[href],[tabindex="0"]')].filter(el=>!el.disabled&&el.getClientRects().length);
      const first=focusable[0],last=focusable.at(-1);
      if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}
      else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}
    });
    // Also restore the page after existing business actions remove their dialog.
    const removal=new MutationObserver(()=>{if(!wrap.isConnected){removal.disconnect();shell.inert=!document.querySelector('#login-screen').classList.contains('hidden')||!!document.querySelector('.modal-backdrop');document.body.style.overflow=document.querySelector('.modal-backdrop')?'hidden':oldOverflow;}});
    removal.observe(document.body,{childList:true});
    decorate(wrap);requestAnimationFrame(()=>[...wrap.querySelectorAll('input:not([type=hidden]):not(:disabled),select,textarea,button')].find(el=>el.getClientRects().length)?.focus());
    return close;
  }
  const navNames={dashboard:'home',orders:'orders',assets:'assets',inventory:'inventory',preventives:'calendar',users:'users'};
  document.querySelectorAll('.nav-item,.bottom-nav-item').forEach(b=>{const span=b.querySelector('span');if(span)span.innerHTML=icon(navNames[b.dataset.view]);});
  const bottom=document.querySelector('#bottom-nav');
  bottom.querySelectorAll('[data-view]:not([data-view="dashboard"]):not([data-view="orders"])').forEach(b=>b.remove());
  bottom.insertAdjacentHTML('beforeend',`<button class="bottom-nav-item" id="more-nav" aria-label="Más módulos" aria-expanded="false" aria-controls="sidebar">${icon('menu')}<span class="nav-label">Más</span></button>`);
  const menu=document.querySelector('#menu');menu.innerHTML=icon('menu');menu.setAttribute('aria-label','Abrir navegación');menu.setAttribute('aria-controls','sidebar');
  const logout=document.querySelector('#logout');logout.innerHTML=icon('logout');logout.setAttribute('aria-label','Cerrar sesión');
  document.querySelector('#mobile-logout').innerHTML=`${icon('logout')}<span>Salir</span>`;
  const notification=document.querySelector('#notification');notification.firstChild.replaceWith(document.createRange().createContextualFragment(icon('bell')));
  const themeToggle=document.querySelector('#theme-toggle');
  const paintTheme=()=>{const dark=document.documentElement.dataset.theme==='dark';themeToggle.innerHTML=icon(dark?'sun':'moon');themeToggle.setAttribute('aria-label',dark?'Cambiar a modo claro':'Cambiar a modo oscuro');themeToggle.title=dark?'Modo claro':'Modo oscuro';document.querySelector('meta[name="theme-color"]').content=dark?'#111827':'#F5F5F7';};
  themeToggle.onclick=()=>{const next=document.documentElement.dataset.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=next;localStorage.setItem('mesa-theme',next);paintTheme();};paintTheme();
  document.querySelector('#fab-new-order')?.removeAttribute('hidden');
  document.querySelector('#more-nav').onclick=()=>document.querySelector('#sidebar').classList.toggle('open');
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!document.querySelector('.modal-backdrop')){document.querySelector('#sidebar').classList.remove('open');menu.focus();}});
  document.addEventListener('click',e=>{if(!e.target.closest('#sidebar,#menu,#more-nav'))document.querySelector('#sidebar').classList.remove('open');});
  new MutationObserver(()=>{const open=document.querySelector('#sidebar').classList.contains('open');menu.setAttribute('aria-expanded',String(open));document.querySelector('#more-nav').setAttribute('aria-expanded',String(open));document.querySelectorAll('.nav-item,.bottom-nav-item[data-view]').forEach(b=>{if(b.classList.contains('active'))b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});}).observe(document.querySelector('#sidebar'),{attributes:true,subtree:true,attributeFilter:['class']});
  const login=document.querySelector('#login-screen');document.querySelector('.app-shell').inert=true;
  new MutationObserver(()=>document.querySelector('.app-shell').inert=!login.classList.contains('hidden')||!!document.querySelector('.modal-backdrop')).observe(login,{attributes:true,attributeFilter:['class']});
  const connection=()=>{const el=document.querySelector('#connection-status');el.hidden=navigator.onLine;el.textContent='Sin conexión. Conserva esta pantalla; los cambios todavía no enviados no se han guardado.';};
  addEventListener('online',connection);addEventListener('offline',connection);connection();
  const content=document.querySelector('#content');new MutationObserver(()=>decorate(content)).observe(content,{childList:true,subtree:true});
  function orderTabs(wrap){
    const grid=wrap.querySelector('.form-grid');const fields=[...grid.children];
    const groups=fields.map(field=>{const label=field.querySelector('label')?.textContent||'';if(label.includes('Insumos'))return 'materials';if(label.includes('Historial')||field.querySelector('a[href*="print"]'))return 'history';if(field.querySelector('.detail-summary')||['Prioridad','Estado','Falla reportada'].includes(label))return 'summary';return 'work';});
    const tabs=document.createElement('div');tabs.className='ui-tabs';tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','Secciones de la orden');
    const items=[['summary','Resumen'],['work','Trabajo'],['materials','Materiales'],['history','Historial']];
    const key=++sequence;
    tabs.innerHTML=items.map(([id,label])=>`<button type="button" role="tab" id="tab-${key}-${id}" aria-controls="panel-${key}-${id}" data-section="${id}">${label}</button>`).join('');
    const panels=items.map(([id])=>{const panel=document.createElement('div');panel.id=`panel-${key}-${id}`;panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby',`tab-${key}-${id}`);panel.className='form-grid full';fields.forEach((f,i)=>{if(groups[i]===id)panel.append(f);});grid.append(panel);return panel;});
    const buttons=[...tabs.children];const choose=id=>{buttons.forEach(b=>{const active=b.dataset.section===id;b.setAttribute('aria-selected',String(active));b.tabIndex=active?0:-1;});panels.forEach((p,i)=>p.hidden=items[i][0]!==id);};
    tabs.onclick=e=>{const b=e.target.closest('[data-section]');if(b)choose(b.dataset.section);};
    tabs.onkeydown=e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();let index=buttons.indexOf(document.activeElement);index=e.key==='Home'?0:e.key==='End'?3:(index+(e.key==='ArrowRight'?1:3))%4;choose(buttons[index].dataset.section);buttons[index].focus();};
    wrap.querySelector('.form').before(tabs);choose('summary');
  }
  return {icon,decorate,dialog,orderTabs};
})();
