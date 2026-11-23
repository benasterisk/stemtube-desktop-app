// Auto remix: a button next to "Open Mixer" that turns an extracted song into a
// new library entry with cleaned, balanced stems in a chosen mixing style. The
// source song is untouched; the copy opens in the mixer like any other song.
(function () {
    let options = null;      // {styles: [{key, label}], default, dry_vocals_default}
    let current = null;      // dataset of the song the dialog is open for
    const running = {};      // download_id -> true while a remix runs

    function csrf() {
        return typeof getCsrfToken === 'function' ? getCsrfToken() : '';
    }

    function toast(message, type) {
        if (typeof showToast === 'function') showToast(message, type || 'info');
    }

    async function loadOptions() {
        if (options) return options;
        const r = await fetch('/api/automix/styles');
        if (!r.ok) throw new Error('HTTP ' + r.status);
        options = await r.json();
        return options;
    }

    function ensureModal() {
        let modal = document.getElementById('autoRemixModal');
        if (modal) return modal;
        modal = document.createElement('div');
        modal.className = 'modal';
        modal.id = 'autoRemixModal';
        modal.innerHTML = `
            <div class="modal-content">
                <div class="modal-header">
                    <h2>Remix automatique</h2>
                    <span class="close-button" id="autoRemixClose">&times;</span>
                </div>
                <div class="modal-body">
                    <div class="audio-info">
                        <h3 id="autoRemixTitle"></h3>
                        <p>Crée une copie du morceau avec des pistes nettoyées, équilibrées et
                           mixées dans le style choisi. L'original n'est pas modifié. La copie
                           s'ouvre dans le mixer avec tous les réglages habituels (volumes,
                           tempo, tonalité).</p>
                    </div>
                    <div class="extraction-options">
                        <div class="option-item">
                            <label for="autoRemixStyle">Style de mixage :</label>
                            <select id="autoRemixStyle" class="stem-model-select"></select>
                        </div>
                        <div class="option-item">
                            <div class="two-stem-mode">
                                <input type="checkbox" id="autoRemixDry">
                                <label for="autoRemixDry">Assécher la voix (retire le son de la pièce ;
                                    modèle de 118 Mo téléchargé au premier usage, lent sans GPU)</label>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="item-button" id="autoRemixCancel">Annuler</button>
                    <button class="item-button extract-button" id="autoRemixStart">
                        <i class="fas fa-magic"></i> Lancer le remix</button>
                </div>
            </div>`;
        document.body.appendChild(modal);
        const close = () => { modal.style.display = 'none'; };
        modal.querySelector('#autoRemixClose').addEventListener('click', close);
        modal.querySelector('#autoRemixCancel').addEventListener('click', close);
        modal.addEventListener('click', (e) => { if (e.target === modal) close(); });
        modal.querySelector('#autoRemixStart').addEventListener('click', start);
        return modal;
    }

    async function openDialog(ds) {
        let opts;
        try {
            opts = await loadOptions();
        } catch (e) {
            toast('Remix automatique indisponible : ' + e.message, 'error');
            return;
        }
        const modal = ensureModal();
        current = { downloadId: ds.downloadId, title: ds.title };
        modal.querySelector('#autoRemixTitle').textContent = ds.title || '';
        const select = modal.querySelector('#autoRemixStyle');
        const last = localStorage.getItem('autoRemixStyle') || opts.default;
        select.innerHTML = '';
        opts.styles.forEach((s) => {
            const o = document.createElement('option');
            o.value = s.key;
            o.textContent = s.label;
            if (s.key === last) o.selected = true;
            select.appendChild(o);
        });
        modal.querySelector('#autoRemixDry').checked = !!opts.dry_vocals_default;
        modal.style.display = 'flex';
    }

    async function start() {
        const modal = ensureModal();
        const style = modal.querySelector('#autoRemixStyle').value;
        const dry = modal.querySelector('#autoRemixDry').checked;
        const id = current && current.downloadId;
        if (!id) return;
        localStorage.setItem('autoRemixStyle', style);
        modal.style.display = 'none';
        try {
            const r = await fetch('/api/automix', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf() },
                body: JSON.stringify({ download_id: Number(id), style: style, dry_vocals: dry })
            });
            const data = await r.json().catch(() => ({}));
            if (!r.ok) throw new Error(data.error || ('HTTP ' + r.status));
            running[id] = true;
            setProgress(id, 0, 'Démarrage');
            toast('Remix automatique lancé : ' + (current.title || ''), 'info');
        } catch (e) {
            toast('Remix automatique : ' + e.message, 'error');
        }
    }

    function buttonFor(id) {
        return document.querySelector(`.autoremix-button[data-download-id="${id}"]`);
    }

    function setProgress(id, pct, message) {
        const btn = buttonFor(id);
        if (!btn) return;
        btn.disabled = true;
        btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${Math.round(pct)}%`;
        btn.title = message || '';
    }

    function resetButton(id) {
        delete running[id];
        const btn = buttonFor(id);
        if (!btn) return;
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-magic"></i>';
        btn.title = 'Remix automatique (crée une copie mixée dans un style)';
    }

    // Called by updateExtractButton() for every extracted song of the library.
    window.addAutoRemixButton = function (mixerButton) {
        const parent = mixerButton.parentNode;
        if (!parent || parent.querySelector('.autoremix-button')) return;
        const ds = mixerButton.dataset;
        if (!ds.downloadId) return;
        const btn = document.createElement('button');
        btn.className = 'item-button autoremix-button';
        btn.dataset.downloadId = ds.downloadId;
        btn.title = 'Remix automatique (crée une copie mixée dans un style)';
        btn.innerHTML = '<i class="fas fa-magic"></i>';
        btn.addEventListener('click', () => openDialog(ds));
        const anchor = parent.querySelector('.reextract-button') || mixerButton;
        anchor.insertAdjacentElement('afterend', btn);
        if (running[ds.downloadId]) setProgress(ds.downloadId, 0, '');
    };

    function wire() {
        if (typeof socket === 'undefined' || !socket) {
            setTimeout(wire, 500);
            return;
        }
        socket.on('automix_progress', (d) => {
            running[d.download_id] = true;
            setProgress(d.download_id, d.progress, d.message);
        });
        socket.on('automix_complete', (d) => {
            resetButton(d.source_download_id);
            toast('Remix prêt : ' + d.title, 'success');
            if (typeof loadDownloads === 'function') loadDownloads();
            if (typeof loadExtractions === 'function') loadExtractions();
        });
        // A song straightened from the mixer (quantize) is a new library entry too.
        socket.on('retime_complete', (d) => {
            toast('Morceau recalé : ' + d.title, 'success');
            if (typeof loadDownloads === 'function') loadDownloads();
            if (typeof loadExtractions === 'function') loadExtractions();
        });
        // A pre-mix made in the mixer from the tracks that play is a new library entry too.
        socket.on('premix_complete', (d) => {
            toast('Pré-mix prêt : ' + d.title, 'success');
            if (typeof loadDownloads === 'function') loadDownloads();
            if (typeof loadExtractions === 'function') loadExtractions();
        });
        socket.on('automix_error', (d) => {
            resetButton(d.download_id);
            toast('Remix automatique : ' + d.error, 'error');
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', wire);
    } else {
        wire();
    }
})();
