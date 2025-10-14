// MediaService API Frontend
class MediaServiceAPI {
    constructor() {
        this.baseURL = 'http://localhost:8001/api/v1';
        this.isOnline = false;
        this.init();
    }

    async init() {
        // Проверяем статус API
        await this.checkAPIStatus();

        // Настраиваем обработчики событий
        this.setupEventHandlers();

        // Загружаем популярные теги
        await this.loadPopularTags();
    }

    async checkAPIStatus() {
        try {
            const response = await fetch(`${this.baseURL}/health`);
            const data = await response.json();

            if (data.status === 'ok') {
                this.isOnline = true;
                this.updateAPIStatus('online', 'API Online');
            } else {
                this.updateAPIStatus('warning', 'API Issues');
            }
        } catch (error) {
            this.isOnline = false;
            this.updateAPIStatus('offline', 'API Offline');
            console.error('API Status Check Failed:', error);
        }
    }

    updateAPIStatus(status, text) {
        const badge = document.getElementById('api-status-badge');
        const statusClasses = {
            'online': 'bg-success',
            'warning': 'bg-warning',
            'offline': 'bg-danger'
        };

        badge.className = `badge ${statusClasses[status]}`;
        badge.innerHTML = `<i class="bi bi-circle-fill"></i> ${text}`;
    }

    setupEventHandlers() {
        // Upload area drag & drop
        const uploadArea = document.getElementById('upload-area');
        const fileInput = document.getElementById('file-input');

        if (uploadArea && fileInput) {
            uploadArea.addEventListener('click', () => fileInput.click());
            uploadArea.addEventListener('dragover', this.handleDragOver);
            uploadArea.addEventListener('dragleave', this.handleDragLeave);
            uploadArea.addEventListener('drop', this.handleDrop.bind(this));

            fileInput.addEventListener('change', this.handleFileSelect.bind(this));
        } else {
            console.warn('Upload area elements not found, drag&drop disabled');
        }

        // Forms
        const uploadForm = document.getElementById('upload-form');
        if (uploadForm) {
            uploadForm.addEventListener('submit', this.handleUpload.bind(this));
        }

        const searchForm = document.getElementById('search-form');
        if (searchForm) {
            searchForm.addEventListener('submit', this.handleSearch.bind(this));
        }

        const timelineForm = document.getElementById('timeline-form');
        if (timelineForm) {
            timelineForm.addEventListener('submit', this.handleTimeline.bind(this));
        }

        // Clear search
        const clearSearchBtn = document.getElementById('clear-search');
        if (clearSearchBtn) {
            clearSearchBtn.addEventListener('click', this.clearSearch.bind(this));
        }

        const searchIdForm = document.getElementById('search-id-form');
        if (searchIdForm) {
            searchIdForm.addEventListener('submit', this.handleSearchById.bind(this));
        }

        const clearSearchIdBtn = document.getElementById('clear-search-id');
        if (clearSearchIdBtn) {
            clearSearchIdBtn.addEventListener('click', this.clearSearchById.bind(this));
        }

        // Tab changes
        const statsTab = document.getElementById('stats-tab');
        if (statsTab) {
            statsTab.addEventListener('click', this.loadStatistics.bind(this));
        }
    }

    handleDragOver(e) {
        e.preventDefault();
        e.currentTarget.classList.add('dragover');
    }

    handleDragLeave(e) {
        e.preventDefault();
        e.currentTarget.classList.remove('dragover');
    }

    handleDrop(e) {
        e.preventDefault();
        e.currentTarget.classList.remove('dragover');

        const files = Array.from(e.dataTransfer.files);
        this.displaySelectedFiles(files);
    }

    handleFileSelect(e) {
        const files = Array.from(e.target.files);
        this.displaySelectedFiles(files);
    }

    displaySelectedFiles(files) {
        const container = document.getElementById('selected-files');
        container.innerHTML = '';

        if (files.length === 0) return;

        files.forEach((file, index) => {
            const fileCard = document.createElement('div');
            fileCard.className = 'border rounded p-3 mb-2 d-flex align-items-center';

            // Иконка файла
            let icon = 'bi-file-earmark';
            if (file.type.startsWith('image/')) icon = 'bi-image';
            else if (file.type.startsWith('video/')) icon = 'bi-camera-video';
            else if (file.type.includes('pdf')) icon = 'bi-file-pdf';

            fileCard.innerHTML = `
                <i class="bi ${icon} fs-4 text-primary me-3"></i>
                <div class="flex-grow-1">
                    <div class="fw-bold">${file.name}</div>
                    <small class="text-muted">${this.formatFileSize(file.size)} • ${file.type}</small>
                </div>
                <button type="button" class="btn btn-sm btn-outline-danger" onclick="this.parentElement.remove()">
                    <i class="bi bi-x"></i>
                </button>
            `;

            container.appendChild(fileCard);
        });

        // Сохраняем файлы для загрузки
        this.selectedFiles = files;
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    async handleUpload(e) {
        e.preventDefault();

        if (!this.selectedFiles || this.selectedFiles.length === 0) {
            this.showAlert('Выберите файлы для загрузки', 'warning');
            return;
        }

        const formData = new FormData();
        const requestNumber = document.getElementById('request-number').value;
        const category = document.getElementById('category').value;
        const description = document.getElementById('description').value;
        const tags = document.getElementById('tags').value;

        // Загружаем файлы по одному
        const results = [];
        const resultsContainer = document.getElementById('upload-results');
        resultsContainer.innerHTML = '<div class="text-center"><div class="spinner-border text-primary"></div><p class="mt-2">Загрузка файлов...</p></div>';

        for (let i = 0; i < this.selectedFiles.length; i++) {
            const file = this.selectedFiles[i];
            const uploadData = new FormData();

            uploadData.append('file', file);
            uploadData.append('request_number', requestNumber);
            uploadData.append('category', category);
            if (description) uploadData.append('description', description);
            if (tags) uploadData.append('tags', tags);

            try {
                const response = await fetch(`${this.baseURL}/media/upload`, {
                    method: 'POST',
                    body: uploadData
                });

                const result = await response.json();

                if (response.ok) {
                    results.push({ success: true, file: file.name, data: result });
                } else {
                    results.push({ success: false, file: file.name, error: result.message || 'Ошибка загрузки' });
                }
            } catch (error) {
                results.push({ success: false, file: file.name, error: error.message });
            }
        }

        this.displayUploadResults(results);

        // Очищаем форму при успешной загрузке
        if (results.every(r => r.success)) {
            document.getElementById('upload-form').reset();
            document.getElementById('selected-files').innerHTML = '';
            this.selectedFiles = [];
        }
    }

    displayUploadResults(results) {
        const container = document.getElementById('upload-results');
        container.innerHTML = '';

        results.forEach(result => {
            const alertType = result.success ? 'success' : 'danger';
            const icon = result.success ? 'bi-check-circle' : 'bi-exclamation-triangle';
            const message = result.success
                ? `${result.file} - Успешно загружен`
                : `${result.file} - ${result.error}`;

            const alert = document.createElement('div');
            alert.className = `alert alert-${alertType} py-2`;
            alert.innerHTML = `<i class="bi ${icon}"></i> ${message}`;
            container.appendChild(alert);
        });
    }

    async handleSearch(e) {
        e.preventDefault();

        const query = document.getElementById('search-query').value;
        const requestNumber = document.getElementById('search-request').value;
        const tags = document.getElementById('search-tags').value;
        const category = document.getElementById('search-category').value;

        const params = new URLSearchParams();
        if (query) params.append('query', query);
        if (requestNumber) params.append('request_numbers', requestNumber);
        if (tags) params.append('tags', tags);
        if (category) params.append('categories', category);
        params.append('limit', '20');

        try {
            const response = await fetch(`${this.baseURL}/media/search?${params}`);
            const data = await response.json();

            if (response.ok) {
                this.displaySearchResults(data);
            } else {
                this.showAlert('Ошибка поиска: ' + (data.message || 'Неизвестная ошибка'), 'danger');
            }
        } catch (error) {
            this.showAlert('Ошибка поиска: ' + error.message, 'danger');
        }
    }

    displaySearchResults(data) {
        const container = document.getElementById('search-results');

        if (!data.results || data.results.length === 0) {
            container.innerHTML = '<div class="alert alert-info"><i class="bi bi-info-circle"></i> Файлы не найдены</div>';
            return;
        }

        container.innerHTML = `
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h6>Найдено: ${data.total_count} файлов</h6>
                <small class="text-muted">Показано: ${data.results.length}</small>
            </div>
        `;

        data.results.forEach(media => {
            const card = this.createMediaCard(media);
            container.appendChild(card);
        });
    }

    createMediaCard(media) {
        const card = document.createElement('div');
        card.className = 'media-card';
        card.setAttribute('data-media-id', media.id);

        const tags = media.tags.map(tag => `<span class="tag">${tag}</span>`).join('');
        const uploadDate = new Date(media.uploaded_at).toLocaleString('ru-RU');

        let preview = '';
        if (media.file_type === 'photo') {
            // Асинхронно получаем URL и загружаем изображение
            preview = `<div class="media-preview d-flex align-items-center justify-content-center">
                <div class="spinner-border spinner-border-sm" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
            </div>`;
            // Загружаем реальное изображение асинхронно (позже, после добавления в DOM)
            setTimeout(() => this.loadImageAsync(media.id), 50);
        } else if (media.file_type === 'video') {
            preview = `<div class="media-preview bg-dark d-flex align-items-center justify-content-center text-white">
                <i class="bi bi-play-circle fs-1"></i>
            </div>`;
        } else {
            preview = `<div class="media-preview bg-light d-flex align-items-center justify-content-center">
                <i class="bi bi-file-earmark fs-1 text-muted"></i>
            </div>`;
        }

        card.innerHTML = `
            <div class="row">
                <div class="col-md-3">
                    ${preview}
                </div>
                <div class="col-md-9">
                    <h6>${media.original_filename}</h6>
                    <p class="text-muted mb-1">${media.description || 'Без описания'}</p>
                    <div class="mb-2">${tags}</div>
                    <div class="row">
                        <div class="col-sm-6">
                            <small><strong>Заявка:</strong> ${media.request_number}</small><br>
                            <small><strong>Категория:</strong> ${media.category}</small>
                        </div>
                        <div class="col-sm-6">
                            <small><strong>Размер:</strong> ${this.formatFileSize(media.file_size)}</small><br>
                            <small><strong>Загружен:</strong> ${uploadDate}</small>
                        </div>
                    </div>
                    <div class="mt-2">
                        <button class="btn btn-sm btn-outline-primary" onclick="mediaAPI.viewMedia(${media.id})">
                            <i class="bi bi-eye"></i> Просмотр
                        </button>
                        <button class="btn btn-sm btn-outline-secondary" onclick="mediaAPI.downloadMedia(${media.id})">
                            <i class="bi bi-download"></i> Скачать
                        </button>
                    </div>
                </div>
            </div>
        `;

        return card;
    }

    async loadImageAsync(mediaId, previewDiv) {
        try {
            const response = await fetch(`${this.baseURL}/media/${mediaId}/url`);
            const data = await response.json();

            if (response.ok && data.file_url) {
                // Заменяем спиннер на реальное изображение
                setTimeout(() => {
                    const previewContainer = document.querySelector(`[data-media-id="${mediaId}"] .media-preview`);
                    if (previewContainer) {
                        previewContainer.innerHTML = `<img src="${data.file_url}" class="img-fluid" alt="Preview">`;
                    }
                }, 100);
            }
        } catch (error) {
            console.error('Failed to load image:', error);
        }
    }

    async viewMedia(mediaId) {
        try {
            const response = await fetch(`${this.baseURL}/media/${mediaId}/url`);
            const data = await response.json();

            if (response.ok && data.file_url) {
                window.open(data.file_url, '_blank');
            } else {
                this.showAlert('Не удалось получить ссылку на файл', 'warning');
            }
        } catch (error) {
            this.showAlert('Ошибка получения ссылки: ' + error.message, 'danger');
        }
    }

    async downloadMedia(mediaId) {
        try {
            const response = await fetch(`${this.baseURL}/media/${mediaId}/url`);
            const data = await response.json();

            if (response.ok && data.file_url) {
                const link = document.createElement('a');
                link.href = data.file_url;
                link.download = '';
                link.click();
            } else {
                this.showAlert('Не удалось получить ссылку на файл', 'warning');
            }
        } catch (error) {
            this.showAlert('Ошибка скачивания: ' + error.message, 'danger');
        }
    }

    clearSearch() {
        document.getElementById('search-form').reset();
        document.getElementById('search-results').innerHTML = '<p class="text-muted text-center">Результаты поиска появятся здесь</p>';
    }

    async handleSearchById(e) {
        e.preventDefault();

        const mediaIdInput = document.getElementById('search-media-id');
        const telegramFileIdInput = document.getElementById('search-telegram-file-id');
        const resultsContainer = document.getElementById('search-id-results');
        const mediaId = mediaIdInput.value.trim();
        const telegramFileId = telegramFileIdInput.value.trim();

        if (!mediaId && !telegramFileId) {
            this.showAlert('Введите ID или Telegram file_id медиа-файла', 'warning');
            return;
        }

        if (mediaId && Number(mediaId) <= 0) {
            this.showAlert('ID медиа-файла должен быть положительным числом', 'warning');
            return;
        }

        resultsContainer.innerHTML = '<div class="text-center"><div class="spinner-border text-primary"></div><p class="mt-2">Загрузка информации о файле...</p></div>';

        try {
            const endpoint = telegramFileId
                ? `${this.baseURL}/media/telegram/${encodeURIComponent(telegramFileId)}`
                : `${this.baseURL}/media/${mediaId}`;

            const response = await fetch(endpoint);
            const data = await response.json();

            if (response.ok) {
                resultsContainer.innerHTML = '';

                if (data.media_file) {
                    const card = this.createMediaCard(data.media_file);
                    if (data.file_url) {
                        card.dataset.fileUrl = data.file_url;
                    }
                    resultsContainer.appendChild(card);
                } else {
                    const card = this.createTelegramLookupCard(data);
                    resultsContainer.appendChild(card);
                }
            } else {
                const message = data.detail || data.message || 'Медиа-файл не найден';
                resultsContainer.innerHTML = `<div class="alert alert-warning"><i class="bi bi-info-circle"></i> ${message}</div>`;
            }
        } catch (error) {
            resultsContainer.innerHTML = `<div class="alert alert-danger"><i class="bi bi-exclamation-triangle"></i> Ошибка поиска: ${error.message}</div>`;
        }
    }

    clearSearchById() {
        document.getElementById('search-id-form').reset();
        document.getElementById('search-id-results').innerHTML = '<p class="text-muted text-center">Введите ID или Telegram file_id медиа-файла для просмотра деталей</p>';
    }

    createTelegramLookupCard(lookup) {
        const card = document.createElement('div');
        card.className = 'media-card';

        const sizeInfo = lookup.file_size ? `<small><strong>Размер:</strong> ${this.formatFileSize(lookup.file_size)}</small><br>` : '';
        const pathInfo = lookup.file_path ? `<small><strong>Путь:</strong> ${lookup.file_path}</small><br>` : '';
        const uniqueInfo = lookup.telegram_file_unique_id
            ? `<small><strong>file_unique_id:</strong> ${lookup.telegram_file_unique_id}</small><br>`
            : '';

        const downloadBlock = lookup.file_url
            ? `<a class="btn btn-sm btn-outline-secondary" href="${lookup.file_url}" target="_blank" rel="noopener">
                    <i class="bi bi-download"></i> Скачать из Telegram
               </a>`
            : '<div class="alert alert-warning py-1 px-2 d-inline-block mb-0"><small>URL недоступен</small></div>';

        card.innerHTML = `
            <div class="row">
                <div class="col-md-3">
                    <div class="media-preview bg-light d-flex align-items-center justify-content-center">
                        <i class="bi bi-telegram fs-1 text-primary"></i>
                    </div>
                </div>
                <div class="col-md-9">
                    <h6>Файл доступен только в Telegram</h6>
                    <p class="text-muted mb-1">Записи в базе Media Service не найдено, но файл доступен по Telegram file_id.</p>
                    <div class="mb-2">
                        <small><strong>Telegram file_id:</strong> ${lookup.telegram_file_id}</small><br>
                        ${uniqueInfo}
                        ${sizeInfo}
                        ${pathInfo}
                    </div>
                    <div class="mt-2">
                        ${downloadBlock}
                    </div>
                </div>
            </div>
        `;

        return card;
    }

    async loadStatistics() {
        const container = document.getElementById('stats-content');

        try {
            container.innerHTML = '<div class="text-center"><div class="spinner-border text-primary"></div><p class="mt-2">Загрузка статистики...</p></div>';

            const response = await fetch(`${this.baseURL}/media/statistics`);
            const stats = await response.json();

            if (response.ok) {
                this.displayStatistics(stats);
            } else {
                container.innerHTML = '<div class="alert alert-danger">Ошибка загрузки статистики</div>';
            }
        } catch (error) {
            container.innerHTML = '<div class="alert alert-danger">Ошибка загрузки статистики: ' + error.message + '</div>';
        }
    }

    displayStatistics(stats) {
        const container = document.getElementById('stats-content');

        container.innerHTML = `
            <div class="row">
                <div class="col-md-3">
                    <div class="stats-card">
                        <h3>${stats.total_files}</h3>
                        <p class="mb-0">Всего файлов</p>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="stats-card">
                        <h3>${stats.total_size_mb} МБ</h3>
                        <p class="mb-0">Общий размер</p>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="stats-card">
                        <h3>${stats.file_types.length}</h3>
                        <p class="mb-0">Типов файлов</p>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="stats-card">
                        <h3>${stats.top_tags.length}</h3>
                        <p class="mb-0">Активных тегов</p>
                    </div>
                </div>
            </div>

            <div class="row mt-4">
                <div class="col-md-6">
                    <div class="card">
                        <div class="card-header">
                            <h6><i class="bi bi-pie-chart"></i> Типы файлов</h6>
                        </div>
                        <div class="card-body">
                            ${stats.file_types.map(type => `
                                <div class="d-flex justify-content-between align-items-center mb-2">
                                    <span>${type.type}</span>
                                    <div>
                                        <span class="badge bg-primary">${type.count}</span>
                                        <small class="text-muted ms-2">${type.size_mb} МБ</small>
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                </div>

                <div class="col-md-6">
                    <div class="card">
                        <div class="card-header">
                            <h6><i class="bi bi-tags"></i> Популярные теги</h6>
                        </div>
                        <div class="card-body">
                            ${stats.top_tags.map(tag => `
                                <div class="d-flex justify-content-between align-items-center mb-2">
                                    <span class="tag">${tag.tag}</span>
                                    <span class="badge bg-secondary">${tag.count}</span>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                </div>
            </div>

            <div class="row mt-4">
                <div class="col-12">
                    <div class="card">
                        <div class="card-header">
                            <h6><i class="bi bi-graph-up"></i> Загрузки по дням (последние 30 дней)</h6>
                        </div>
                        <div class="card-body">
                            ${stats.daily_uploads.length > 0 ? stats.daily_uploads.map(day => `
                                <div class="d-flex justify-content-between align-items-center mb-1">
                                    <span>${day.date}</span>
                                    <span class="badge bg-info">${day.count} файлов</span>
                                </div>
                            `).join('') : '<p class="text-muted">Нет данных за последние 30 дней</p>'}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    async handleTimeline(e) {
        e.preventDefault();

        const requestNumber = document.getElementById('timeline-request').value;
        const container = document.getElementById('timeline-results');

        try {
            container.innerHTML = '<div class="text-center"><div class="spinner-border text-primary"></div><p class="mt-2">Загрузка временной линии...</p></div>';

            const response = await fetch(`${this.baseURL}/media/request/${requestNumber}/timeline`);
            const data = await response.json();

            if (response.ok) {
                this.displayTimeline(data);
            } else {
                container.innerHTML = '<div class="alert alert-danger">Ошибка загрузки временной линии</div>';
            }
        } catch (error) {
            container.innerHTML = '<div class="alert alert-danger">Ошибка: ' + error.message + '</div>';
        }
    }

    displayTimeline(data) {
        const container = document.getElementById('timeline-results');

        if (!data.timeline || data.timeline.length === 0) {
            container.innerHTML = '<div class="alert alert-info">Медиа-файлы для данной заявки не найдены</div>';
            return;
        }

        container.innerHTML = `
            <h6 class="mb-3">Заявка ${data.request_number} - ${data.total_files} файлов</h6>
            ${data.timeline.map(item => {
                const time = new Date(item.timestamp).toLocaleString('ru-RU');
                const tags = item.tags.map(tag => `<span class="tag">${tag}</span>`).join('');

                return `
                    <div class="timeline-item">
                        <div class="d-flex justify-content-between align-items-start mb-2">
                            <h6 class="mb-1">${item.filename}</h6>
                            <small class="text-muted">${time}</small>
                        </div>
                        <p class="text-muted mb-1">${item.description || 'Без описания'}</p>
                        <div class="mb-2">${tags}</div>
                        <small>
                            <span class="badge bg-light text-dark">${item.file_type}</span>
                            <span class="badge bg-light text-dark">${item.category}</span>
                            <span class="badge bg-light text-dark">${this.formatFileSize(item.file_size)}</span>
                        </small>
                    </div>
                `;
            }).join('')}
        `;
    }

    async loadPopularTags() {
        try {
            const response = await fetch(`${this.baseURL}/media/tags/popular?limit=10`);
            const tags = await response.json();

            if (response.ok) {
                this.popularTags = tags;
            }
        } catch (error) {
            console.warn('Не удалось загрузить популярные теги:', error);
        }
    }

    showAlert(message, type = 'info') {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
        alertDiv.style.cssText = 'top: 70px; right: 20px; z-index: 1050; max-width: 400px;';
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;

        document.body.appendChild(alertDiv);

        // Автоматически скрываем через 5 секунд
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.remove();
            }
        }, 5000);
    }
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    window.mediaAPI = new MediaServiceAPI();
});

// Проверяем статус API каждые 30 секунд
setInterval(() => {
    if (window.mediaAPI) {
        window.mediaAPI.checkAPIStatus();
    }
}, 30000);
