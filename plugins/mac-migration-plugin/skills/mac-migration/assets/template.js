  const STORAGE_KEY = 'mac-migration-v2';
  const THEME_KEY = 'mac-migration-theme';

  const sunPath = 'M12 1v2m0 18v2M4.22 4.22l1.42 1.42m12.72 12.72l1.42 1.42M1 12h2m18 0h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10z';
  const moonPath = 'M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z';

  function getTheme() {
    return localStorage.getItem(THEME_KEY) || 'dark';
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(THEME_KEY, theme);
    const icon = document.getElementById('themeIcon');
    const label = document.getElementById('themeLabel');
    if (theme === 'dark') {
      icon.innerHTML = `<path d="${sunPath}"/>`;
      label.textContent = 'Light';
    } else {
      icon.innerHTML = `<path d="${moonPath}"/>`;
      label.textContent = 'Dark';
    }
  }

  function toggleTheme() {
    applyTheme(getTheme() === 'dark' ? 'light' : 'dark');
  }

  function getState() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {} }
    catch { return {} }
  }

  function saveState(s) { localStorage.setItem(STORAGE_KEY, JSON.stringify(s)) }

  function toggleExpand(e, btn) {
    e.stopPropagation();
    btn.closest('.item-expandable').classList.toggle('expanded');
  }

  function setupItem(item) {
    const cb = item.querySelector('input[type="checkbox"]');
    const state = getState();
    const val = state[item.dataset.id];
    if (val === 'skipped') {
      cb.checked = true;
      item.classList.add('skipped');
    } else if (val) {
      cb.checked = true;
      item.classList.add('checked');
    }

    let pressTimer = null;
    let didLongPress = false;

    cb.addEventListener('pointerdown', (e) => {
      didLongPress = false;
      pressTimer = setTimeout(() => {
        didLongPress = true;
        e.preventDefault();
        toggleSkip(item, cb);
      }, 500);
    });

    cb.addEventListener('pointerup', () => { clearTimeout(pressTimer) });
    cb.addEventListener('pointerleave', () => { clearTimeout(pressTimer) });

    cb.addEventListener('change', () => {
      if (didLongPress) {
        // Undo the default toggle that the change event caused
        const s = getState();
        if (s[item.dataset.id] === 'skipped') {
          cb.checked = true;
        }
        return;
      }
      // If currently skipped, a normal click clears the skip
      if (item.classList.contains('skipped')) {
        item.classList.remove('skipped');
        cb.checked = false;
        const s = getState();
        delete s[item.dataset.id];
        saveState(s);
        updateProgress();
        return;
      }
      toggle(item, cb);
    });
  }

  function init() {
    applyTheme(getTheme());
    document.querySelectorAll('.item[data-id], .item-expandable[data-id]').forEach(setupItem);
    updateProgress();
    observeSections();
  }

  function toggle(item, cb) {
    const state = getState();
    state[item.dataset.id] = cb.checked;
    saveState(state);
    if (cb.checked) {
      item.classList.remove('skipped');
      item.classList.add('checked', 'just-checked');
      setTimeout(() => item.classList.remove('just-checked'), 250);
    } else {
      item.classList.remove('checked', 'skipped');
    }
    updateProgress();
  }

  function toggleSkip(item, cb) {
    const state = getState();
    if (item.classList.contains('skipped')) {
      // Unskip
      item.classList.remove('skipped');
      cb.checked = false;
      delete state[item.dataset.id];
    } else {
      // Skip
      item.classList.remove('checked');
      item.classList.add('skipped');
      cb.checked = true;
      state[item.dataset.id] = 'skipped';
    }
    saveState(state);
    updateProgress();
  }

  function updateProgress() {
    const all = document.querySelectorAll('[data-id]');
    const done = document.querySelectorAll('[data-id].checked, [data-id].skipped').length;
    const pct = all.length ? Math.round((done / all.length) * 100) : 0;
    document.getElementById('progressFill').style.width = pct + '%';
    document.getElementById('progressPct').textContent = pct + '%';

    // Section counts
    document.querySelectorAll('.section').forEach(sec => {
      const id = sec.id;
      const total = sec.querySelectorAll('[data-id]').length;
      const checked = sec.querySelectorAll('[data-id].checked, [data-id].skipped').length;
      const el = sec.querySelector('.section-count');
      if (el) el.textContent = checked + '/' + total;
      const tocCount = document.querySelector(`.toc-count[data-toc="${id}"]`);
      if (tocCount) tocCount.textContent = checked + '/' + total;
    });
  }

  function resetAll() {
    if (!confirm('Reset all checkboxes? This cannot be undone.')) return;
    localStorage.removeItem(STORAGE_KEY);
    document.querySelectorAll('[data-id]').forEach(item => {
      item.classList.remove('checked', 'skipped');
      item.querySelector('input[type="checkbox"]').checked = false;
    });
    updateProgress();
    showToast('All items reset');
  }

  function copyPath(e, btn, path) {
    e.preventDefault();
    e.stopPropagation();
    navigator.clipboard.writeText(path).then(() => {
      const label = btn.querySelector('span');
      label.textContent = 'copied!';
      btn.classList.add('copied');
      showToast('Path copied to clipboard');
      setTimeout(() => { label.textContent = 'copy path'; btn.classList.remove('copied') }, 2000);
    });
  }

  function copyCmd(el) {
    const text = el.querySelector('code').textContent.replace(/^\$ /, '');
    navigator.clipboard.writeText(text).then(() => {
      const label = el.querySelector('.cmd-copy');
      label.textContent = 'copied!';
      label.classList.add('copied');
      showToast('Copied to clipboard');
      setTimeout(() => { label.textContent = 'click to copy'; label.classList.remove('copied') }, 2000);
    });
  }

  function showToast(msg) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 1800);
  }

  // Sidebar active state based on scroll
  function observeSections() {
    const sections = document.querySelectorAll('.section');
    const tocItems = document.querySelectorAll('.toc-item');
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          tocItems.forEach(t => t.classList.remove('active'));
          const match = document.querySelector(`.toc-item[href="#${entry.target.id}"]`);
          if (match) match.classList.add('active');
        }
      });
    }, { rootMargin: '-20% 0px -70% 0px' });
    sections.forEach(s => observer.observe(s));
  }

  // Mobile sidebar
  function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('open');
    document.getElementById('sidebarOverlay').classList.toggle('open');
  }

  // Close sidebar on nav click (mobile)
  document.querySelectorAll('.toc-item').forEach(a => {
    a.addEventListener('click', () => {
      if (window.innerWidth <= 860) toggleSidebar();
    });
  });

  document.addEventListener('DOMContentLoaded', init);
