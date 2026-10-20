(() => {
  'use strict';
  const maxSize = 8 * 1024 * 1024;
  const formats = ['image/jpeg', 'image/png', 'image/webp'];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const fileError = file => !file.size ? 'Selecciona una imagen con contenido.' : file.size > maxSize ? 'La imagen debe pesar como máximo 8 MB.' :
    !formats.includes(file.type) ? 'Usa una imagen JPG, PNG o WebP.' : '';

  function field(name, title) {
    const id = `order-${name}`;
    return `<div class="field full order-image-field"><label for="${id}">${esc(title)} <span class="subtle">(opcional)</span></label>
      <input id="${id}" name="${name}" type="file" accept="${formats.join(',')}" aria-describedby="${id}-help ${id}-error" data-order-image>
      <small id="${id}-help" class="subtle">Selecciona una foto o usa la cámara del teléfono. JPG, PNG o WebP, hasta 8 MB.</small>
      <p id="${id}-error" class="order-image-error" role="status" aria-live="polite" hidden></p>
      <div class="order-image-preview" hidden><img alt="Vista previa de la imagen seleccionada"><button type="button" class="btn btn-secondary" data-remove-image>Quitar imagen seleccionada</button></div></div>`;
  }

  function bind(root) {
    const cleaners = [];
    root.querySelectorAll('[data-order-image]').forEach(input => {
      const container = input.closest('.order-image-field');
      const preview = container.querySelector('.order-image-preview');
      const image = preview.querySelector('img');
      const error = container.querySelector('[role="status"]');
      let url;
      const clear = () => { if (url) URL.revokeObjectURL(url); url = null; image.removeAttribute('src'); };
      cleaners.push(clear);
      input.addEventListener('change', () => {
        clear();
        const file = input.files[0];
        const message = file ? fileError(file) : '';
        input.setCustomValidity(message);
        input.setAttribute('aria-invalid', message ? 'true' : 'false');
        error.textContent = message;
        error.hidden = !message;
        preview.hidden = !file || Boolean(message);
        if (file && !message) { url = URL.createObjectURL(file); image.src = url; }
      });
      container.querySelector('[data-remove-image]').addEventListener('click', () => {
        input.value = '';
        input.dispatchEvent(new Event('change', {bubbles:true}));
        input.focus();
      });
    });
    if (cleaners.length) {
      const observer = new MutationObserver(() => {
        if (!root.isConnected) { cleaners.forEach(clean => clean()); observer.disconnect(); }
      });
      observer.observe(root.parentNode, {childList:true});
    }
  }

  function body(data) {
    const fields = {...data};
    const attachments = [];
    for (const name of ['report_image', 'completion_image']) {
      const file = fields[name];
      delete fields[name];
      if (file instanceof File && file.name) {
        const message = fileError(file);
        if (message) throw new Error(message);
        attachments.push([name, file]);
      }
    }
    if (!attachments.length) return JSON.stringify(fields);
    const form = new FormData();
    form.append('data', JSON.stringify(fields));
    attachments.forEach(([name, file]) => form.append(name, file));
    return form;
  }

  function gallery(images = []) {
    return `<section class="field full order-image-evidence" aria-labelledby="order-image-title"><h3 id="order-image-title">Evidencia fotográfica</h3>${images.length ?
      `<div class="order-image-gallery">${images.map(image => {
        const title = image.kind === 'report' ? 'Falla reportada' : 'Trabajo terminado';
        const date = new Date(image.created_at).toLocaleString('es-MX');
        return `<figure><a href="${esc(image.url)}" target="_blank" rel="noopener noreferrer" aria-label="Abrir imagen: ${title}"><img src="${esc(image.url)}" alt="${title}" loading="lazy" width="${Number(image.width)}" height="${Number(image.height)}"></a><figcaption><strong>${title}</strong><small>${esc(image.created_by)} · ${esc(date)}</small><a href="${esc(image.url)}" target="_blank" rel="noopener noreferrer">Abrir imagen completa</a></figcaption></figure>`;
      }).join('')}</div>` : '<p class="subtle">Sin imágenes adjuntas.</p>'}</section>`;
  }

  window.MesaOrderImages = {field, bind, body, gallery};
})();
