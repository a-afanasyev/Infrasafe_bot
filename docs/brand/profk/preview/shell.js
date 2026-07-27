/* Общий каркас консоли менеджера (сайдбар + топбар) для превью PROFK.
   Заполняет #sidebar и #topbar по data-* на <body>. Контент страницы — как есть. */
(function () {
  const I = (p) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
  const NAV = [
    ['analytics', 'Аналитика', '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>'],
    ['requests', 'Заявки', '<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/>'],
    ['employees', 'Сотрудники', '<circle cx="9" cy="8" r="3.5"/><path d="M3 20c0-3.5 3-5.5 6-5.5s6 2 6 5.5"/><path d="M16 5a3.5 3.5 0 010 6M18 20c0-2.5-1-4-2.5-5"/>'],
    ['shifts', 'Смены', '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'],
    ['addresses', 'Адреса', '<path d="M12 21s-7-6-7-11a7 7 0 0114 0c0 5-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/>'],
    ['access', 'Контроль доступа', '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>'],
    ['materials', 'Склад', '<path d="M3 7l9-4 9 4-9 4-9-4z"/><path d="M3 7v10l9 4 9-4V7"/><path d="M12 11v10"/>'],
  ];
  const active = document.body.dataset.nav || '';
  const title = document.body.dataset.title || '';
  const actions = document.body.dataset.actions || '';

  const sb = document.getElementById('sidebar');
  if (sb) {
    sb.className = 'sidebar';
    sb.innerHTML =
      `<div class="sidebar-brand">
         <img src="assets/profk-mark.svg" alt="PROFK">
         <div><div class="bt">PROFK</div><div class="bs">PRO FACILITY KOMMUNAL</div></div>
       </div>
       <div class="nav-section">Основное</div>
       <nav class="nav">
         ${NAV.map(([id, label, p]) => `<a class="nav-item ${id === active ? 'active' : ''}" href="manager-${id === 'requests' ? 'kanban' : id}.html">${I(p)}<span>${label}</span></a>`).join('')}
       </nav>
       <div style="padding:14px;border-top:1px solid var(--border-soft)">
         <div class="flex center gap12">
           <div class="avatar">МД</div>
           <div><div style="font-family:var(--font-display);font-weight:700;font-size:13px">Мурод Д.</div>
           <div class="mut" style="font-size:11px">Менеджер</div></div>
         </div>
       </div>`;
  }

  const tb = document.getElementById('topbar');
  if (tb) {
    tb.className = 'topbar';
    tb.innerHTML =
      `<div style="font-family:var(--font-display);font-weight:800;font-size:18px">${title}</div>
       <div class="spacer"></div>
       ${actions}
       <div class="flex gap8 center" style="margin-left:6px">
         <span class="chip active" style="padding:4px 10px">Ru</span>
         <span class="chip" style="padding:4px 10px">O'z</span>
       </div>
       <div class="avatar">МД</div>`;
  }
})();
