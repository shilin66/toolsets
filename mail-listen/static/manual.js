/* Progressive enhancement: Markdown and native anchors remain readable without JS. */
(() => {
  const article = document.querySelector('.manual-content article');
  const headings = [...article.querySelectorAll('h2, h3')];
  const chapters = [...article.querySelectorAll('h2')];
  const chapterLinks = [...document.querySelectorAll('[data-chapter]')];
  const sectionGroups = [...document.querySelectorAll('[data-for]')];
  const sectionLinks = [...document.querySelectorAll('.manual-toc a')];
  const breadcrumb = document.getElementById('manual-current-chapter');
  const search = document.getElementById('manual-search');
  const results = document.getElementById('manual-search-results');
  const status = document.getElementById('manual-search-status');
  const preview = document.querySelector('.manual-image-preview');
  const previewImage = preview.querySelector('img');

  article.addEventListener('click', event => {
    const link = event.target.closest('.manual-image-link');
    if (!link) return;
    event.preventDefault();
    previewImage.src = link.href;
    previewImage.alt = link.querySelector('img').alt;
    preview.showModal();
    document.body.classList.add('manual-preview-open');
  });
  preview.addEventListener('click', event => {
    if (event.target === preview) preview.close();
  });
  preview.querySelector('.manual-preview-close').addEventListener('click', () => preview.close());
  preview.addEventListener('close', () => {
    document.body.classList.remove('manual-preview-open');
  });

  const index = headings.map(heading => {
    let body = '';
    for (let next = heading.nextElementSibling; next && !/^H[23]$/.test(next.tagName); next = next.nextElementSibling) {
      body += ' ' + next.textContent;
    }
    return { id: heading.id, title: heading.textContent, body: body.replace(/\s+/g, ' ').trim() };
  });

  const setCurrent = (link, current) => {
    if (current) link.setAttribute('aria-current', 'location');
    else link.removeAttribute('aria-current');
  };
  let scheduled = false;
  const updateNavigation = () => {
    scheduled = false;
    const chapter = chapters.filter(heading => heading.getBoundingClientRect().top <= 120).pop() || chapters[0];
    const current = headings.filter(heading => heading.getBoundingClientRect().top <= 120).pop() || chapter;
    chapterLinks.forEach(link => setCurrent(link, link.dataset.chapter === chapter.id));
    sectionGroups.forEach(group => { group.hidden = group.dataset.for !== chapter.id; });
    sectionLinks.forEach(link => setCurrent(link, decodeURIComponent(link.hash.slice(1)) === current.id));
    breadcrumb.textContent = chapter.textContent;
  };
  const scheduleNavigation = () => {
    if (!scheduled) {
      scheduled = true;
      requestAnimationFrame(updateNavigation);
    }
  };
  window.addEventListener('scroll', scheduleNavigation, { passive: true });
  window.addEventListener('hashchange', scheduleNavigation);
  window.addEventListener('load', scheduleNavigation);
  window.addEventListener('resize', scheduleNavigation);
  updateNavigation();

  const clearSearch = () => {
    search.value = '';
    results.replaceChildren();
    results.hidden = true;
    status.textContent = '';
  };
  search.addEventListener('input', () => {
    const query = search.value.trim().toLocaleLowerCase();
    results.replaceChildren();
    results.hidden = !query;
    if (!query) { status.textContent = ''; return; }
    const matches = index.filter(item => (item.title + ' ' + item.body).toLocaleLowerCase().includes(query))
      .sort((a, b) => Number(b.title.toLocaleLowerCase().includes(query)) - Number(a.title.toLocaleLowerCase().includes(query)));
    status.textContent = matches.length ? `找到 ${matches.length} 个相关小节，显示前 ${Math.min(matches.length, 12)} 个` : '没有找到相关内容';
    if (!matches.length) {
      const empty = document.createElement('p');
      empty.textContent = '没有找到相关内容，请换一个关键词。';
      results.append(empty);
    }
    matches.slice(0, 12).forEach(item => {
      const link = document.createElement('a');
      link.href = '#' + item.id;
      const title = document.createElement('strong');
      title.textContent = item.title;
      const snippet = document.createElement('span');
      const start = Math.max(0, item.body.toLocaleLowerCase().indexOf(query) - 14);
      snippet.textContent = (start ? '…' : '') + item.body.slice(start, start + 72) + (item.body.length > start + 72 ? '…' : '');
      link.append(title, snippet);
      link.addEventListener('click', () => {
        // Preserve native anchor navigation, then move keyboard focus into the article.
        const heading = document.getElementById(item.id);
        heading.tabIndex = -1;
        heading.focus({ preventScroll: true });
        setTimeout(clearSearch, 0);
      });
      results.append(link);
    });
  });
  search.addEventListener('keydown', event => {
    if (event.key === 'ArrowDown' && results.firstElementChild?.tagName === 'A') {
      event.preventDefault();
      results.firstElementChild.focus();
    }
  });
  document.addEventListener('keydown', event => {
    if (preview.open) return;
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      search.focus();
      search.select();
    } else if (event.key === 'Escape' && !results.hidden) {
      clearSearch();
      search.focus();
    }
  });
})();
