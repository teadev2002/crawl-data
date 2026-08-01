document.addEventListener('DOMContentLoaded', () => {
    // TAB NAVIGATION
    const navTabs = document.querySelectorAll('.nav-tab');
    const tabPanes = document.querySelectorAll('.tab-pane');

    navTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            navTabs.forEach(t => t.classList.remove('active'));
            tabPanes.forEach(p => p.classList.remove('active'));
            
            tab.classList.add('active');
            const targetPane = document.getElementById(tab.dataset.tab);
            if (targetPane) targetPane.classList.add('active');

            if (tab.dataset.tab === 'tab-data' || tab.dataset.tab === 'tab-dashboard') {
                loadTableData();
            }
        });
    });

    // TOOL PROGRESS & LOCALSTORAGE FILE OUTPUT HELPERS
    function setToolFile(toolKey, filename) {
        if (!filename) return;
        try {
            localStorage.setItem(`active_file_${toolKey}`, filename);
        } catch (e) {
            console.warn('LocalStorage disabled or blocked:', e);
        }
        const el = document.getElementById(`file-output-${toolKey}`);
        if (el) el.innerText = filename;
    }

    function initToolFiles() {
        const tools = ['map', 'email', 'cat', 'info'];
        tools.forEach(key => {
            let saved = null;
            try {
                saved = localStorage.getItem(`active_file_${key}`);
            } catch (e) {
                console.warn('LocalStorage disabled or blocked:', e);
            }
            const el = document.getElementById(`file-output-${key}`);
            if (el) {
                el.innerText = (saved && saved !== 'Chưa chọn') ? saved : 'Chưa chạy';
            }
        });
    }

    // Nạp tên file output từ LocalStorage (nếu đã từng kích hoạt chạy trước đó)
    initToolFiles();

    function updateToolStatus(toolKey, status, labelText) {
        const badge = document.getElementById(`badge-${toolKey}-status`);
        if (!badge) return;
        badge.className = `tool-status-badge ${status}`;
        badge.innerText = labelText || (status === 'running' ? 'Đang chạy' : status === 'completed' ? 'Hoàn thành' : 'Sẵn sàng');
    }

    function updateToolProgress(toolKey, current, total) {
        if (!total || total <= 0) return;
        const percent = Math.min(100, Math.round((current / total) * 1000) / 10);
        const txtEl = document.getElementById(`prog-text-${toolKey}`);
        const pctEl = document.getElementById(`prog-percent-${toolKey}`);
        const barEl = document.getElementById(`prog-bar-${toolKey}`);

        if (txtEl) txtEl.innerText = `${current} / ${total} bản ghi`;
        if (pctEl) pctEl.innerText = `${percent}%`;
        if (barEl) barEl.style.width = `${percent}%`;
    }

    let progressTotals = { map: 100, email: 100, cat: 100, info: 10 };
    let progressCurrents = { map: 0, email: 0, cat: 0, info: 0 };
    let mapActiveThreads = new Set();

    function parseLogProgress(msg) {
        // Quản lý trạng thái 5 luồng (P1 -> P5) hoặc 2 luồng (TOP & BOTTOM) của MAP SCRAPER
        const workerMatchStart = msg.match(/\[MAP_(P[1-5]|TOP|BOTTOM)\] Đã khởi chạy/i);
        if (workerMatchStart) {
            mapActiveThreads.add(workerMatchStart[1].toLowerCase());
            updateToolStatus('map', 'running', 'Đang cào');
        }
        const workerMatchFinish = msg.match(/\[MAP_(P[1-5]|TOP|BOTTOM)\]/i) && msg.includes('đã hoàn thành');
        if (workerMatchFinish) {
            const finishedWorker = msg.match(/\[MAP_(P[1-5]|TOP|BOTTOM)\]/i)[1].toLowerCase();
            mapActiveThreads.delete(finishedWorker);
        }

        // Tự động nhận diện Tên File Output thực tế từ WebSocket Log khi bất kỳ tool nào khởi chạy
        const fileMatch = msg.match(/Đang đọc file dữ liệu:\s*([^\s\n]+)/i) || msg.match(/File lưu dữ liệu:\s*([^\s\n]+)/i);
        if (fileMatch) {
            const activeFile = fileMatch[1].trim();
            if (msg.includes('CategoryName') || msg.includes('cat_repair') || msg.includes('Category')) {
                setToolFile('cat', activeFile);
                updateToolStatus('cat', 'running', 'Đang dò');
            } else if (msg.includes('Info_Repair') || msg.includes('info_repairer') || msg.includes("dính lỗi 'N/A'")) {
                setToolFile('info', activeFile);
                updateToolStatus('info', 'running', 'Đang sửa');
            } else if (msg.includes('EMAIL') || msg.includes('email_harvester') || msg.includes('thiếu email')) {
                setToolFile('email', activeFile);
                updateToolStatus('email', 'running', 'Đang quét');
            } else if (msg.includes('MAP') || msg.includes('map_scraper')) {
                setToolFile('map', activeFile);
                updateToolStatus('map', 'running', 'Đang cào');
            }
        }

        const isCatLog = msg.includes('CategoryName') || msg.includes('cat_repair') || msg.includes('Category');
        const isInfoLog = msg.includes('Info_Repair') || msg.includes('info_repairer') || msg.includes("dính lỗi 'N/A'");
        const isEmailLog = msg.includes('EMAIL') || msg.includes('email_harvester') || msg.includes('thiếu email');
        const isMapLog = msg.includes('MAP') || msg.includes('map_scraper') || msg.includes('cào google maps');

        // 1. MAP SCRAPER
        if (isMapLog || msg.includes('Real-Time Save #')) {
            const mapMaxMatch = msg.match(/Số kết quả tối đa:\s*(\d+)/i);
            if (mapMaxMatch) {
                progressTotals.map = parseInt(mapMaxMatch[1]) || progressTotals.map;
                updateToolProgress('map', progressCurrents.map, progressTotals.map);
            }
            const mapSaveMatch = msg.match(/Real-Time Save #(\d+)/i);
            if (mapSaveMatch) {
                const newSaveCount = parseInt(mapSaveMatch[1]);
                if (newSaveCount > progressCurrents.map) {
                    progressCurrents.map = newSaveCount;
                    updateToolProgress('map', progressCurrents.map, progressTotals.map);
                }
                updateToolStatus('map', 'running', 'Đang cào');
            }
            // CHỈ đổi sang badge HOÀN THÀNH khi CẢ 2 LUỒNG (TOP & BOTTOM) đều đã phát ra log báo hoàn thành
            const isMapFinished = msg.includes('Hoàn thành! Đã quét thêm') || msg.includes('Tổng số kết quả hiện tại trong file') || (msg.includes('MAP') && msg.includes('đã hoàn thành'));
            if (isMapFinished && mapActiveThreads.size === 0) {
                updateToolProgress('map', progressCurrents.map, progressTotals.map);
                updateToolStatus('map', 'completed', 'Hoàn thành');
            }
        }

        // 2. EMAIL HARVESTER
        if (isEmailLog && !isCatLog && !isInfoLog) {
            const emailFileTotalMatch = msg.match(/Tổng số bản ghi trong file:\s*(\d+)/i);
            if (emailFileTotalMatch) {
                progressTotals.email = parseInt(emailFileTotalMatch[1]) || 100;
                updateToolProgress('email', progressCurrents.email, progressTotals.email);
                updateToolStatus('email', 'running', 'Đang quét');
            }
            const emailFlaggedMatch = msg.match(/Đã quét\s*(\d+)\/(\d+)\s*bản ghi/i);
            if (emailFlaggedMatch) {
                progressCurrents.email = parseInt(emailFlaggedMatch[1]);
                progressTotals.email = parseInt(emailFlaggedMatch[2]) || progressTotals.email;
                updateToolProgress('email', progressCurrents.email, progressTotals.email);
                updateToolStatus('email', 'running', 'Đang quét');
            }
            if (msg.includes('QUÉT EMAIL HOÀN TẤT!') || msg.includes('quét email hoàn thành')) {
                updateToolProgress('email', progressTotals.email, progressTotals.email);
                updateToolStatus('email', 'completed', 'Hoàn thành');
            }
        }

        // 3. CATEGORY REPAIRER
        if (isCatLog) {
            const catTotalMatch = msg.match(/Phát hiện (\d+) bản ghi/i);
            if (catTotalMatch) {
                progressTotals.cat = parseInt(catTotalMatch[1]) || 100;
                progressCurrents.cat = 0;
                updateToolProgress('cat', 0, progressTotals.cat);
                updateToolStatus('cat', 'running', 'Đang dò');
            }
            const catProgressMatch = msg.match(/\[CategoryName\] Đang phục hồi \[(\d+)\/(\d+)\]/i) || msg.match(/CategoryName/i);
            if (catProgressMatch) {
                if (catProgressMatch[1] && catProgressMatch[2]) {
                    progressCurrents.cat = parseInt(catProgressMatch[1]);
                    progressTotals.cat = parseInt(catProgressMatch[2]) || progressTotals.cat;
                } else if (msg.includes('Real-Time Save STT') || msg.includes('categoryName:')) {
                    progressCurrents.cat += 1;
                }
                updateToolProgress('cat', progressCurrents.cat, progressTotals.cat);
                updateToolStatus('cat', 'running', 'Đang dò');
            }
            if (msg.includes('PHỤC HỒI HOÀN TẤT!') || msg.includes('dò category hoàn thành')) {
                updateToolProgress('cat', progressTotals.cat, progressTotals.cat);
                updateToolStatus('cat', 'completed', 'Hoàn thành');
            }
        }

        // 4. INFO REPAIRER
        if (isInfoLog) {
            const infoTotalMatch = msg.match(/Phát hiện (\d+) bản ghi bị dính lỗi 'N\/A'/i);
            if (infoTotalMatch) {
                progressTotals.info = parseInt(infoTotalMatch[1]) || 10;
                progressCurrents.info = 0;
                updateToolProgress('info', 0, progressTotals.info);
                updateToolStatus('info', 'running', 'Đang sửa');
            }
            const infoSavedMatch = msg.match(/Đã sửa (\d+)\/(\d+) bản ghi N\/A/i);
            if (infoSavedMatch) {
                progressCurrents.info = parseInt(infoSavedMatch[1]);
                progressTotals.info = parseInt(infoSavedMatch[2]) || progressTotals.info;
                updateToolProgress('info', progressCurrents.info, progressTotals.info);
                updateToolStatus('info', 'running', 'Đang sửa');
            } else {
                const infoProgressMatch = msg.match(/\[Info_Repair\] Đang phục hồi \[(\d+)\/(\d+)\]/i);
                if (infoProgressMatch) {
                    progressCurrents.info = Math.max(0, parseInt(infoProgressMatch[1]) - 1);
                    progressTotals.info = parseInt(infoProgressMatch[2]) || progressTotals.info;
                    updateToolProgress('info', progressCurrents.info, progressTotals.info);
                    updateToolStatus('info', 'running', 'Đang sửa');
                }
            }
            if (msg.includes('PHỤC HỒI DỮ LIỆU N/A HOÀN TẤT!') || msg.includes('sửa dữ liệu n\/a hoàn thành')) {
                updateToolProgress('info', progressTotals.info, progressTotals.info);
                updateToolStatus('info', 'completed', 'Hoàn thành');
            }
        }
    }

    // WEBSOCKET LOG STREAM
    let ws = null;
    function connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/logs`;
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            appendLog('[*] Đã kết nối thành công với WebSocket Live Log.', 'sys');
            document.getElementById('server-status-text').innerText = 'Server: Sẵn sàng';
        };

        ws.onmessage = (event) => {
            const msg = event.data;
            let type = 'sys';
            if (msg.includes('✓') || msg.includes('Thành công') || msg.includes('[+]')) type = 'success';
            else if (msg.includes('!') || msg.includes('Cảnh báo') || msg.includes('[-]')) type = 'warn';
            else if (msg.includes('Lỗi') || msg.includes('Traceback')) type = 'error';

            appendLog(msg, type);

            // Bóc tách tiến trình Real-Time từ WebSocket log
            parseLogProgress(msg);

            // Bật Toast Notification nếu dính Captcha
            if (msg.includes('PHÁT HIỆN CAPTCHA GOOGLE')) {
                showToast('PHÁT HIỆN CAPTCHA GOOGLE! Vui lòng thao tác trên trình duyệt đang mở.', 'warning', 10000);
            }

            // Tự động làm mới bảng và thẻ thống kê nếu có lưu Real-Time mới hoặc tiến trình hoàn thành
            if (msg.includes('Real-Time Save') || msg.includes('Thành công - STT') || msg.includes('hoàn thành!') || msg.includes('Hoàn thành!')) {
                loadTableData();
            }
        };

        ws.onclose = () => {
            document.getElementById('server-status-text').innerText = 'Server: Mất kết nối';
            setTimeout(connectWebSocket, 3000);
        };
    }
    connectWebSocket();

    // LOG APPENDER
    const consoleOutput = document.getElementById('console-output');
    const chkAutoScroll = document.getElementById('chk-autoscroll');

    function appendLog(text, type = 'sys') {
        const div = document.createElement('div');
        div.className = `log-line ${type}`;
        div.innerText = text;
        consoleOutput.appendChild(div);

        if (chkAutoScroll.checked) {
            consoleOutput.scrollTop = consoleOutput.scrollHeight;
        }
    }

    document.getElementById('btn-clear-console').addEventListener('click', () => {
        consoleOutput.innerHTML = '<div class="log-line sys">[*] Đã xóa nhật ký.</div>';
    });



    // TOAST NOTIFICATION HELPER
    function showToast(message, type = 'warning', duration = 8000) {
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'toast-container';
            document.body.appendChild(container);
        }
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `<i class="fa-solid fa-triangle-exclamation toast-icon"></i> <span>${message}</span>`;
        container.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(120%)';
            toast.style.transition = 'all 0.3s ease';
            setTimeout(() => toast.remove(), 350);
        }, duration);
    }

    // SERVICE MODE EXCLUSIVE TOGGLE LOGIC
    const serviceToggles = document.querySelectorAll('.service-toggle');
    const serviceStatusBadge = document.getElementById('service-status-badge');

    function updateServiceBadge(serviceName) {
        if (!serviceStatusBadge) return;
        if (serviceName === 'hotel') {
            serviceStatusBadge.innerText = 'Đang Bật: Khách sạn & Lưu trú';
            serviceStatusBadge.style.background = 'rgba(96, 165, 250, 0.2)';
            serviceStatusBadge.style.color = '#60a5fa';
        } else if (serviceName === 'restaurant') {
            serviceStatusBadge.innerText = 'Đang Bật: Nhà hàng & Ăn uống';
            serviceStatusBadge.style.background = 'rgba(245, 158, 11, 0.2)';
            serviceStatusBadge.style.color = '#f59e0b';
        } else if (serviceName === 'spa') {
            serviceStatusBadge.innerText = 'Đang Bật: Spa & Massage';
            serviceStatusBadge.style.background = 'rgba(236, 72, 153, 0.2)';
            serviceStatusBadge.style.color = '#ec4899';
        } else {
            serviceStatusBadge.innerText = 'TẮT BỘ LỌC (Cào tất cả địa điểm)';
            serviceStatusBadge.style.background = 'rgba(156, 163, 175, 0.2)';
            serviceStatusBadge.style.color = '#9ca3af';
        }
    }

    function setServiceMode(selectedService) {
        serviceToggles.forEach(chk => {
            const isTarget = selectedService !== 'none' && chk.dataset.service === selectedService;
            chk.checked = isTarget;
            const cardItem = document.getElementById(`item-service-${chk.dataset.service}`);
            if (cardItem) {
                if (isTarget) cardItem.classList.add('active');
                else cardItem.classList.remove('active');
            }
        });
        updateServiceBadge(selectedService);
    }

    serviceToggles.forEach(chk => {
        chk.addEventListener('change', (e) => {
            if (e.target.checked) {
                setServiceMode(e.target.dataset.service);
            } else {
                setServiceMode('none');
            }
        });
    });

    // EMAIL HARVEST MODE EXCLUSIVE TOGGLE (Bắt buộc 1 trong 2 ON, không cho TẮT cả 2)
    const chkFindAll = document.getElementById('cfg-find-all');
    const chkFindNext = document.getElementById('cfg-find-next');

    if (chkFindAll && chkFindNext) {
        chkFindAll.addEventListener('change', () => {
            if (chkFindAll.checked) {
                chkFindNext.checked = false;
            } else {
                chkFindNext.checked = true;
            }
        });

        chkFindNext.addEventListener('change', () => {
            if (chkFindNext.checked) {
                chkFindAll.checked = false;
            } else {
                chkFindAll.checked = true;
            }
        });
    }

    // CONFIG MANAGEMENT
    async function loadConfig() {
        try {
            const res = await fetch('/api/config');
            const cfg = await res.json();

            const queries = cfg.search_queries || [];
            const searchQueriesEl = document.getElementById('cfg-search-queries');
            if (searchQueriesEl) searchQueriesEl.value = queries.join('\n');
            
            const badgeEl = document.getElementById('query-count-badge');
            if (badgeEl) badgeEl.innerText = `${queries.length} từ khóa`;

            window.currentConfigOutputFile = cfg.output_file || 'hotels.json';

            const outputFileEl = document.getElementById('cfg-output-file');
            if (outputFileEl) outputFileEl.value = window.currentConfigOutputFile;

            const maxResultsEl = document.getElementById('cfg-max-results');
            if (maxResultsEl) {
                maxResultsEl.value = cfg.max_results || 100;
                const syncMaxResults = () => {
                    const val = parseInt(maxResultsEl.value);
                    if (val && val > 0) {
                        progressTotals.map = val;
                        updateToolProgress('map', progressCurrents.map, progressTotals.map);
                    }
                };
                maxResultsEl.addEventListener('input', syncMaxResults);
                maxResultsEl.addEventListener('change', syncMaxResults);
                syncMaxResults();
            }

            const captchaSoundEl = document.getElementById('cfg-captcha-sound');
            if (captchaSoundEl) captchaSoundEl.checked = !!cfg.capcha_sound;
            
            const targetProvinceEl = document.getElementById('cfg-target-province');
            if (targetProvinceEl && cfg.target_province) targetProvinceEl.value = cfg.target_province;

            // Xử lý nạp cấu hình 1 trong 2 chế độ cào email luôn ON
            if (chkFindAll && chkFindNext) {
                if (cfg.findNext && !cfg.findAll) {
                    chkFindAll.checked = false;
                    chkFindNext.checked = true;
                } else {
                    chkFindAll.checked = true;
                    chkFindNext.checked = false;
                }
            }

            const activeService = cfg.target_service || 'hotel';
            setServiceMode(activeService);

            // Nạp tên file output theo từng chức năng từ LocalStorage (nếu có)
            initToolFiles();
        } catch (err) {
            appendLog(`[!] Lỗi khi nạp cấu hình: ${err}`, 'error');
        }
    }
    loadConfig();

    document.getElementById('btn-save-config').addEventListener('click', async () => {
        const searchQueriesEl = document.getElementById('cfg-search-queries');
        const rawQueries = searchQueriesEl ? searchQueriesEl.value : '';
        const queries = rawQueries.split('\n').map(q => q.trim()).filter(q => q.length > 0);

        let selectedService = 'none';
        serviceToggles.forEach(chk => {
            if (chk.checked) selectedService = chk.dataset.service;
        });

        const outputFileEl = document.getElementById('cfg-output-file');
        const maxResultsEl = document.getElementById('cfg-max-results');
        const captchaSoundEl = document.getElementById('cfg-captcha-sound');
        const targetProvinceEl = document.getElementById('cfg-target-province');
        const newMaxResults = maxResultsEl ? (parseInt(maxResultsEl.value) || 50) : 50;

        const payload = {
            search_queries: queries,
            output_file: outputFileEl ? outputFileEl.value.trim() : 'hotels.json',
            max_results: newMaxResults,
            USE_MY_CHROME_PROFILE: false,
            capcha_sound: captchaSoundEl ? captchaSoundEl.checked : false,
            findAll: chkFindAll ? chkFindAll.checked : true,
            findNext: chkFindNext ? chkFindNext.checked : false,
            target_service: selectedService,
            target_province: targetProvinceEl ? targetProvinceEl.value : 'all'
        };

        try {
            const res = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (data.status === 'success') {
                progressTotals.map = newMaxResults;
                updateToolProgress('map', progressCurrents.map, progressTotals.map);
                appendLog(`[+] Đã lưu cấu hình config.json thành công (Max results: ${newMaxResults}, Dịch vụ: ${selectedService.toUpperCase()})!`, 'success');
                document.getElementById('query-count-badge').innerText = `${queries.length} từ khóa`;
                await loadTableData();
                alert('Đã lưu cấu hình thành công! Dữ liệu và mẫu số đã được tự động làm mới.');
            }
        } catch (err) {
            appendLog(`[!] Lỗi khi lưu cấu hình: ${err}`, 'error');
        }
    });

    // SCRAPER CONTROLS
    async function triggerTask(actionPath) {
        try {
            let res = await fetch(`/api/tasks/${actionPath}`, { method: 'POST' });
            if (!res.ok && actionPath === 'start/map_5way') {
                res = await fetch(`/api/tasks/start/map_dual`, { method: 'POST' });
            }
            const data = await res.json();
            appendLog(`[*] ${data.message}`, 'sys');
        } catch (err) {
            appendLog(`[!] Lỗi khi gọi lệnh: ${err}`, 'error');
        }
    }

    function getCurrentOutputFile() {
        const outputFileEl = document.getElementById('cfg-output-file');
        let val = outputFileEl ? outputFileEl.value.trim() : '';
        if (!val || val === 'Chưa chọn' || val === 'Chưa chạy') {
            val = window.currentConfigOutputFile || 'hotels.json';
        }
        return val;
    }

    // Cấu hình lựa chọn Radio số luồng cào Maps (3, 4, 5 luồng)
    const mapThreadRadios = document.querySelectorAll('input[name="map-thread-count"]');
    const btnStartMap = document.getElementById('btn-start-map-action') || document.getElementById('btn-start-map-5way') || document.getElementById('btn-start-map-dual');
    
    function getSelectedMapThreads() {
        let val = '5';
        mapThreadRadios.forEach(radio => {
            if (radio.checked) val = radio.value;
        });
        return val;
    }

    mapThreadRadios.forEach(radio => {
        radio.addEventListener('change', () => {
            const num = getSelectedMapThreads();
            if (btnStartMap) {
                btnStartMap.innerHTML = `<i class="fa-solid fa-rocket"></i> Chạy ${num} Luồng (Song song)`;
            }
        });
    });

    if (btnStartMap) {
        btnStartMap.addEventListener('click', () => {
            const maxResultsEl = document.getElementById('cfg-max-results');
            if (maxResultsEl) {
                const currentMax = parseInt(maxResultsEl.value) || progressTotals.map;
                progressTotals.map = currentMax;
                updateToolProgress('map', progressCurrents.map, progressTotals.map);
            }
            const curFile = getCurrentOutputFile();
            setToolFile('map', curFile);
            updateToolStatus('map', 'running', 'Đang cào');
            const numThreads = getSelectedMapThreads();
            triggerTask(`start/map_${numThreads}way`);
        });
    }

    document.getElementById('btn-start-email-dual').addEventListener('click', () => {
        const curFile = getCurrentOutputFile();
        setToolFile('email', curFile);
        updateToolStatus('email', 'running', 'Đang quét');
        triggerTask('start/email_dual');
    });

    document.getElementById('btn-start-cat-repair').addEventListener('click', () => {
        const curFile = getCurrentOutputFile();
        setToolFile('cat', curFile);
        updateToolStatus('cat', 'running', 'Đang dò');
        triggerTask('start/cat_repair');
    });

    document.getElementById('btn-start-info-repair').addEventListener('click', () => {
        const curFile = getCurrentOutputFile();
        setToolFile('info', curFile);
        updateToolStatus('info', 'running', 'Đang sửa');
        triggerTask('start/info_repair');
    });

    // DATA EXPLORER & EXPORT
    let allRecords = [];
    let currentPage = 1;
    const pageSize = 50;

    async function loadTableData() {
        try {
            const res = await fetch('/api/records');
            const data = await res.json();
            allRecords = data.records || [];
            updateStats(allRecords);
            populateCategoryFilter(allRecords);
            renderTable(allRecords);
        } catch (err) {
            appendLog(`[!] Lỗi khi đọc dữ liệu bảng: ${err}`, 'error');
        }
    }

    function updateStats(records) {
        document.getElementById('stat-total-records').innerText = records.length;

        let emailCount = 0;
        let categoryCount = 0;
        let phoneCount = 0;
        let flaggedCount = 0;

        records.forEach(r => {
            if (r.email && r.email.trim() !== '') emailCount++;
            if (r.categoryName && r.categoryName.trim() !== '' && r.categoryName !== 'N/A') categoryCount++;
            if (r.phone && r.phone.trim() !== '') phoneCount++;
            if (r.isFlag === true) flaggedCount++;
        });

        document.getElementById('stat-email-records').innerText = emailCount;
        document.getElementById('stat-category-records').innerText = categoryCount;
        document.getElementById('stat-phone-records').innerText = phoneCount;

        // Đồng bộ tiến trình Cào Google Maps chính xác theo tổng số bản ghi thực tế trong file output
        if (records.length > 0) {
            progressCurrents.map = Math.max(progressCurrents.map, records.length);
            updateToolProgress('map', progressCurrents.map, progressTotals.map);
        }

        // Đồng bộ tiến trình Quét Email chính xác theo số bản ghi đã đánh dấu isFlag=True
        const emailBadge = document.getElementById('badge-email-status');
        if (emailBadge && emailBadge.classList.contains('running') && records.length > 0) {
            progressCurrents.email = flaggedCount;
            progressTotals.email = records.length;
            updateToolProgress('email', progressCurrents.email, progressTotals.map ? progressTotals.email : records.length);
        }
    }

    function populateCategoryFilter(records) {
        const catSelect = document.getElementById('data-filter-category');
        const currentSelected = catSelect.value;
        const categories = new Set();
        records.forEach(r => {
            if (r.categoryName && r.categoryName.trim() !== '' && r.categoryName !== 'N/A') {
                categories.add(r.categoryName.trim());
            }
        });

        catSelect.innerHTML = '<option value="all">Tất cả CategoryName</option>';
        Array.from(categories).sort().forEach(cat => {
            const opt = document.createElement('option');
            opt.value = cat;
            opt.innerText = cat;
            if (cat === currentSelected) opt.selected = true;
            catSelect.appendChild(opt);
        });
    }

    function renderTable(records) {
        const tbody = document.getElementById('table-body');
        const searchKw = document.getElementById('data-search-input').value.toLowerCase().trim();
        const emailFilter = document.getElementById('data-filter-email').value;
        const catFilter = document.getElementById('data-filter-category').value;

        const filtered = records.filter(r => {
            // Search keyword
            const textContent = `${r.title} ${r.phone} ${r.address} ${r.email} ${r.categoryName}`.toLowerCase();
            if (searchKw && !textContent.includes(searchKw)) return false;

            // Email Filter
            if (emailFilter === 'has_email' && (!r.email || r.email.trim() === '')) return false;
            if (emailFilter === 'no_email' && r.email && r.email.trim() !== '') return false;

            // Category Filter
            if (catFilter !== 'all' && r.categoryName !== catFilter) return false;

            return true;
        });

        const totalRecords = filtered.length;
        const totalPages = Math.ceil(totalRecords / pageSize) || 1;

        if (currentPage > totalPages) currentPage = totalPages;
        if (currentPage < 1) currentPage = 1;

        const startIndex = (currentPage - 1) * pageSize;
        const endIndex = Math.min(startIndex + pageSize, totalRecords);
        const pageData = filtered.slice(startIndex, endIndex);

        if (filtered.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-center">Không tìm thấy bản ghi phù hợp.</td></tr>';
            document.getElementById('pagination-info').innerText = 'Hiển thị 0 - 0 trong tổng số 0 bản ghi';
            document.getElementById('page-indicator').innerText = 'Trang 1 / 1';
            document.getElementById('btn-prev-page').disabled = true;
            document.getElementById('btn-next-page').disabled = true;
            return;
        }

        tbody.innerHTML = pageData.map((r, idx) => `
            <tr>
                <td>${r.stt || startIndex + idx + 1}</td>
                <td><strong>${escapeHtml(r.title || 'N/A')}</strong></td>
                <td><span class="badge blue">${escapeHtml(r.categoryName || 'Chưa có')}</span></td>
                <td>${r.email ? `<span class="badge green">${escapeHtml(r.email)}</span>` : '<span class="text-muted">-</span>'}</td>
                <td>${escapeHtml(r.phone || '-')}</td>
                <td><small>${escapeHtml(r.address || '-')}</small></td>
                <td>${r.totalScore ? `⭐ ${r.totalScore}` : '-'}</td>
                <td>${r.website ? `<a href="${r.website}" target="_blank" rel="noopener">Link</a>` : '-'}</td>
            </tr>
        `).join('');

        // Update Pagination Controls & Info
        document.getElementById('pagination-info').innerText = `Hiển thị ${startIndex + 1} - ${endIndex} trong tổng số ${totalRecords} bản ghi`;
        document.getElementById('page-indicator').innerText = `Trang ${currentPage} / ${totalPages}`;
        document.getElementById('btn-prev-page').disabled = (currentPage <= 1);
        document.getElementById('btn-next-page').disabled = (currentPage >= totalPages);
    }

    function escapeHtml(str) {
        return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    // FILTER & PAGINATION EVENT LISTENERS
    document.getElementById('data-search-input').addEventListener('input', () => {
        currentPage = 1;
        renderTable(allRecords);
    });

    document.getElementById('data-filter-email').addEventListener('change', () => {
        currentPage = 1;
        renderTable(allRecords);
    });

    document.getElementById('data-filter-category').addEventListener('change', () => {
        currentPage = 1;
        renderTable(allRecords);
    });

    document.getElementById('btn-refresh-table').addEventListener('click', loadTableData);

    document.getElementById('btn-prev-page').addEventListener('click', () => {
        if (currentPage > 1) {
            currentPage--;
            renderTable(allRecords);
        }
    });

    document.getElementById('btn-next-page').addEventListener('click', () => {
        const searchKw = document.getElementById('data-search-input').value.toLowerCase().trim();
        const emailFilter = document.getElementById('data-filter-email').value;
        const catFilter = document.getElementById('data-filter-category').value;
        const filteredCount = allRecords.filter(r => {
            const textContent = `${r.title} ${r.phone} ${r.address} ${r.email} ${r.categoryName}`.toLowerCase();
            if (searchKw && !textContent.includes(searchKw)) return false;
            if (emailFilter === 'has_email' && (!r.email || r.email.trim() === '')) return false;
            if (emailFilter === 'no_email' && r.email && r.email.trim() !== '') return false;
            if (catFilter !== 'all' && r.categoryName !== catFilter) return false;
            return true;
        }).length;
        const totalPages = Math.ceil(filteredCount / pageSize) || 1;

        if (currentPage < totalPages) {
            currentPage++;
            renderTable(allRecords);
        }
    });

    // EXPORT BUTTONS
    document.getElementById('btn-export-excel').addEventListener('click', () => {
        window.location.href = '/api/records/export/excel';
    });

    document.getElementById('btn-export-csv').addEventListener('click', () => {
        window.location.href = '/api/records/export/csv';
    });

    document.getElementById('btn-download-json').addEventListener('click', () => {
        window.location.href = '/api/records/export/json';
    });

    // Initial Data Load
    loadTableData();
});
