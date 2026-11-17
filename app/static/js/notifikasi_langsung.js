/*
 * Sprint 3 backlog 2 (PRD 5.2, uc_i_push_notifikasi.feature): live notification badge and toast.
 *
 * Every `interval_detik` seconds (SCMS_POLL_NOTIF_DETIK, default 15) the citizen's page asks
 * GET /api/notifikasi/belum-dibaca for the unread count and the newest unread notifications.
 *   - #badgeNotif shows the new count (created or removed as needed), without reloading the page.
 *   - A notification that was not on screen yet raises the in-page toast #toastNotif.
 *   - If the citizen allowed browser notifications, it is also shown with the Notification API.
 *     Permission "denied" or a browser without the API falls back to the toast only.
 * No Web Push, VAPID or service worker: polling only runs while a citizen page is open.
 */
(function () {
    'use strict';

    var elKonfig = document.getElementById('konfigNotifLangsung');
    if (!elKonfig) return;
    var konfig;
    try { konfig = JSON.parse(elKonfig.textContent); } catch (e) { return; }

    var intervalMs = Math.max(1, Number(konfig.interval_detik) || 15) * 1000;
    var terlihat = {};
    (konfig.terlihat || []).forEach(function (id) { terlihat[id] = true; });
    var berhenti = false;
    var pewaktu = null;
    var pewaktuToast = null;

    function adaApiNotifikasi() {
        return typeof window.Notification === 'function';
    }

    // ------------------------------------------------------------------ badge
    function perbaruiBadge(jumlah) {
        var menu = document.getElementById('menuNotifikasi');
        if (!menu) return;
        var badge = document.getElementById('badgeNotif');
        if (!jumlah) {
            if (badge) badge.remove();
            return;
        }
        if (!badge) {
            badge = document.createElement('span');
            badge.id = 'badgeNotif';
            badge.className = menu.getAttribute('data-kelas-badge') ||
                'ml-1 min-w-[18px] h-[18px] px-1 rounded-full bg-red-600 text-white text-[10px] font-extrabold inline-flex items-center justify-center';
            menu.appendChild(badge);
        }
        badge.textContent = String(jumlah);
        menu.setAttribute('aria-label', 'Notifikasi, ' + jumlah + ' belum dibaca');
    }

    // ------------------------------------------------------------------ toast
    // The `hidden` attribute (not Tailwind's .hidden class) so the toast also hides on pages
    // whose stylesheet has not loaded yet.
    function tampilkanToast(n) {
        var toast = document.getElementById('toastNotif');
        if (!toast) return;
        document.getElementById('toastNotifJudul').textContent = n.judul;
        document.getElementById('toastNotifPesan').textContent = n.pesan;
        document.getElementById('toastNotifBuka').setAttribute('href', n.url);
        toast.hidden = false;
        clearTimeout(pewaktuToast);
        // stays long enough to read; hovering keeps it open
        pewaktuToast = setTimeout(sembunyikanToast, 12000);
    }

    function sembunyikanToast() {
        var toast = document.getElementById('toastNotif');
        if (toast && !toast.matches(':hover')) toast.hidden = true;
        else if (toast) pewaktuToast = setTimeout(sembunyikanToast, 3000);
    }

    var tombolTutup = document.getElementById('toastNotifTutup');
    if (tombolTutup) {
        tombolTutup.addEventListener('click', function () {
            clearTimeout(pewaktuToast);
            document.getElementById('toastNotif').hidden = true;
        });
    }

    // ------------------------------------------------- browser notification
    function tampilkanNotifikasiBrowser(n) {
        if (!adaApiNotifikasi() || window.Notification.permission !== 'granted') return;
        try {
            var notif = new window.Notification('Status laporan ' + n.id_laporan + ' diperbarui', {
                body: n.pesan,
                tag: n.id,
                icon: '/static/images/logo.png'
            });
            notif.onclick = function () {
                window.focus();
                window.location.href = n.url;
            };
        } catch (e) {
            // e.g. mobile Chrome only allows notifications from a service worker: the toast is enough
        }
    }

    // ------------------------------------------------------------------ poll
    function proses(data) {
        perbaruiBadge(data.jumlah || 0);
        var baru = (data.terbaru || []).filter(function (n) { return !terlihat[n.id]; });
        baru.forEach(function (n) { terlihat[n.id] = true; });
        if (!baru.length) return;
        tampilkanToast(baru[0]);  // newest first
        baru.slice(0, 3).forEach(tampilkanNotifikasiBrowser);
    }

    function jadwalkan() {
        clearTimeout(pewaktu);
        if (!berhenti) pewaktu = setTimeout(tanya, intervalMs);
    }

    // Polls even while the tab is hidden: that is exactly when a browser notification is useful,
    // and a window covered by another one counts as hidden on Windows. Browsers already slow down
    // timers in background tabs on their own.
    function tanya() {
        fetch(konfig.url, {credentials: 'same-origin', cache: 'no-store', headers: {'Accept': 'application/json'}})
            .then(function (r) {
                if (r.status === 401 || r.status === 403) { berhenti = true; return null; }  // logged out
                return r.ok ? r.json() : null;
            })
            .then(function (data) { if (data) proses(data); })
            .catch(function () { /* offline for a moment: try again next round */ })
            .then(jadwalkan);
    }

    // Coming back to the tab: check right away instead of waiting for the next round.
    document.addEventListener('visibilitychange', function () {
        if (!document.hidden && !berhenti) { clearTimeout(pewaktu); tanya(); }
    });

    // --------------------------------------- opt-in button on /notifikasi
    var tombolIzin = document.getElementById('aktifkanNotifBrowser');
    var infoIzin = document.getElementById('infoNotifBrowser');
    function perbaruiTombolIzin() {
        if (!tombolIzin) return;
        var izin = adaApiNotifikasi() ? window.Notification.permission : 'unsupported';
        tombolIzin.classList.toggle('hidden', izin !== 'default');
        if (infoIzin) {
            infoIzin.textContent = izin === 'granted' ? 'Notifikasi browser aktif.'
                : izin === 'denied' ? 'Notifikasi browser diblokir di pengaturan browser; kabar terbaru tetap muncul di halaman ini.'
                : '';
        }
    }
    if (tombolIzin) {
        tombolIzin.addEventListener('click', function () {
            if (!adaApiNotifikasi()) return;
            try {
                var hasil = window.Notification.requestPermission(perbaruiTombolIzin);
                if (hasil && typeof hasil.then === 'function') hasil.then(perbaruiTombolIzin, perbaruiTombolIzin);
            } catch (e) { perbaruiTombolIzin(); }
        });
    }
    perbaruiTombolIzin();

    jadwalkan();
})();
