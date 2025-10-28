# ТЕХНИЧЕСКОЕ ЗАДАНИЕ
## Telegram WebApp для Менеджера Управляющей Компании

**Проект**: UK Management Bot - Manager WebApp Module
**Платформа**: Telegram WebApp
**Версия**: 2.0.0 (Оптимизировано под WebApp)
**Дата**: 19 октября 2025
**Статус**: ✅ Готово к реализации

---

## 📋 СОДЕРЖАНИЕ

1. [Обзор проекта](#обзор-проекта)
2. [Преимущества Telegram WebApp](#преимущества-telegram-webapp)
3. [Функциональные требования](#функциональные-требования)
4. [Техническая архитектура](#техническая-архитектура)
5. [Двусторонняя интеграция](#двусторонняя-интеграция)
6. [API спецификация](#api-спецификация)
7. [Структура проекта](#структура-проекта)
8. [План разработки](#план-разработки)

---

## 🎯 ОБЗОР ПРОЕКТА

### Цель
Создать удобный Telegram WebApp для менеджеров управляющей компании с визуальной канбан-доской заявок, управлением сменами и полной интеграцией с существующим ботом.

### Ключевые особенности
- ✅ **Нативная интеграция** с Telegram - работает внутри мессенджера
- ✅ **Двусторонняя синхронизация** - все изменения видны и в WebApp, и в боте
- ✅ **Real-time обновления** - WebSocket для мгновенной синхронизации
- ✅ **Использование существующих сервисов** - интеграция с 26+ сервисами бота
- ✅ **Адаптивный дизайн** - оптимизация для ПК, планшетов и мобильных
- ✅ **AI-powered** - интеграция с SmartDispatcher и AssignmentOptimizer

### Проблематика
Текущий Telegram-бот оптимизирован для мобильных устройств:
- ❌ Нет визуальной канбан-доски для управления заявками
- ❌ Неудобно работать с множественными заявками одновременно
- ❌ Отсутствует обзор всех смен на календаре
- ❌ Сложно выполнять массовые операции
- ❌ Ограниченная аналитика и визуализация KPI

### Решение
Telegram WebApp предоставляет:
- ✅ Визуальную канбан-доску с drag-and-drop (для desktop)
- ✅ Календарь смен с обзором на месяц
- ✅ Дашборд с KPI и аналитикой
- ✅ Массовые операции с заявками
- ✅ ИИ-назначения одним кликом

---

## 🚀 ПРЕИМУЩЕСТВА TELEGRAM WEBAPP

### Почему Telegram WebApp?

#### ✅ Технические преимущества
```yaml
Авторизация:
  - Автоматическая через Telegram (initData)
  - Нет необходимости в отдельной регистрации
  - JWT токены для API

Инфраструктура:
  - Использует существующий FastAPI backend
  - Интеграция с 26+ готовыми сервисами
  - Docker контейнеры уже настроены

Разработка:
  - 3 недели вместо 8 недель (standalone app)
  - Меньше кода, меньше поддержки
  - Проще тестирование

Безопасность:
  - Встроенная валидация Telegram
  - HTTPS обязателен
  - CORS настроен автоматически
```

#### ✅ Бизнес-преимущества
```yaml
Пользовательский опыт:
  - Не нужно устанавливать отдельное приложение
  - Работает сразу из Telegram
  - Единая экосистема для всех ролей

Скорость запуска:
  - MVP за 2-3 недели
  - Быстрая проверка концепции
  - Сбор feedback от менеджеров

Стоимость:
  - Минимальные затраты на инфраструктуру
  - Используем существующие серверы
  - Не нужен отдельный домен
```

#### ⚠️ Ограничения (и как мы их решаем)
```yaml
Ограничение 1: Работает только в Telegram
Решение: Это нормально, все пользователи уже в Telegram

Ограничение 2: Размер экрана в iframe
Решение: Адаптивный дизайн, fullscreen режим

Ограничение 3: Нет desktop версии вне Telegram
Решение: Telegram Desktop поддерживает WebApp

Ограничение 4: Ограничения browser API
Решение: Используем только поддерживаемые API
```

---

## 📋 ФУНКЦИОНАЛЬНЫЕ ТРЕБОВАНИЯ

### 1. Авторизация (Telegram Native)

#### 1.1 Telegram WebApp initData
```javascript
// Frontend получает initData автоматически
const initData = window.Telegram.WebApp.initData;
const initDataUnsafe = window.Telegram.WebApp.initDataUnsafe;

// Структура initDataUnsafe
{
  user: {
    id: 123456789,
    first_name: "Иван",
    last_name: "Менеджеров",
    username: "ivanov",
    language_code: "ru"
  },
  auth_date: 1697634000,
  hash: "abc123def456..."
}
```

#### 1.2 Backend валидация
```python
# POST /api/manager/auth/telegram
async def telegram_auth(initData: str):
    # 1. Валидация hash (HMAC-SHA256)
    # 2. Проверка auth_date (< 24 часа)
    # 3. Проверка роли пользователя (manager)
    # 4. Генерация JWT токенов
    return {
        "access_token": "eyJ0eXAiOiJKV1Q...",
        "refresh_token": "eyJ0eXAiOiJKV1Q...",
        "user": {...}
    }
```

### 2. Канбан-доска заявок

#### 2.1 Визуализация
```
┌─────────────────────────────────────────────────────────────────┐
│ Канбан-доска заявок                         [Фильтры] [Поиск]  │
├─────────────────────────────────────────────────────────────────┤
│ [Все категории ▼] [Все срочности ▼] [Все исполнители ▼]        │
├──────────┬──────────┬──────────┬──────────┬──────────┬─────────┤
│ Новые(8) │В работе  │ Закуп(3) │Уточнен(4)│Выполнены │Исполнено│
│          │  (22)    │          │          │  (15)    │  (10)   │
├──────────┼──────────┼──────────┼──────────┼──────────┼─────────┤
│          │          │          │          │          │         │
│ [Card 1] │ [Card 5] │ [Card 9] │[Card 12] │[Card 15] │[Card 20]│
│ [Card 2] │ [Card 6] │[Card 10] │[Card 13] │[Card 16] │         │
│ [Card 3] │ [Card 7] │[Card 11] │[Card 14] │          │         │
│ [Card 4] │ [Card 8] │          │          │          │         │
│          │          │          │          │          │         │
└──────────┴──────────┴──────────┴──────────┴──────────┴─────────┘
```

#### 2.2 Карточка заявки
```vue
<template>
  <v-card
    class="request-card"
    :class="urgencyClass"
    @click="openDetails"
  >
    <!-- Заголовок -->
    <v-card-title class="py-2">
      <span class="text-subtitle-1">#{{ request.request_number }}</span>
      <v-spacer></v-spacer>
      <v-chip
        :color="urgencyColor"
        size="small"
        label
      >
        {{ request.urgency }}
      </v-chip>
    </v-card-title>

    <!-- Содержимое -->
    <v-card-text class="py-2">
      <div class="text-body-2 mb-2">
        <v-icon size="small">mdi-map-marker</v-icon>
        {{ request.address }}
      </div>

      <div class="text-body-2 mb-2">
        <v-icon size="small">mdi-tag</v-icon>
        {{ request.category }}
      </div>

      <div class="text-caption text-truncate">
        {{ request.description }}
      </div>
    </v-card-text>

    <!-- Футер -->
    <v-card-actions class="py-1">
      <v-avatar size="24" v-if="request.executor">
        <v-img :src="request.executor.photo_url"></v-img>
      </v-avatar>
      <span class="text-caption">
        {{ formatTime(request.created_at) }}
      </span>
      <v-spacer></v-spacer>
      <v-chip size="x-small" v-if="request.media_files.length">
        <v-icon size="x-small">mdi-camera</v-icon>
        {{ request.media_files.length }}
      </v-chip>
    </v-card-actions>
  </v-card>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  request: Object
})

const urgencyColor = computed(() => {
  const colors = {
    'Обычная': 'success',
    'Средняя': 'warning',
    'Срочная': 'error',
    'Критическая': 'error darken-2'
  }
  return colors[props.request.urgency] || 'grey'
})

const urgencyClass = computed(() => {
  return `urgency-${props.request.urgency.toLowerCase()}`
})

const emit = defineEmits(['open-details'])

const openDetails = () => {
  emit('open-details', props.request)
}

const formatTime = (date) => {
  // Форматирование времени
  const now = new Date()
  const created = new Date(date)
  const diff = now - created

  if (diff < 3600000) return `${Math.floor(diff / 60000)}мин`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}ч`
  return `${Math.floor(diff / 86400000)}д`
}
</script>
```

#### 2.3 Фильтрация и поиск
```vue
<template>
  <v-row class="mb-4">
    <!-- Поиск -->
    <v-col cols="12" md="4">
      <v-text-field
        v-model="search"
        prepend-inner-icon="mdi-magnify"
        label="Поиск по номеру, адресу, описанию"
        variant="outlined"
        density="compact"
        clearable
        @input="onSearch"
      ></v-text-field>
    </v-col>

    <!-- Фильтр по категории -->
    <v-col cols="12" sm="6" md="3">
      <v-select
        v-model="filters.category"
        :items="categories"
        label="Категория"
        variant="outlined"
        density="compact"
        clearable
        @update:model-value="onFilterChange"
      ></v-select>
    </v-col>

    <!-- Фильтр по срочности -->
    <v-col cols="12" sm="6" md="3">
      <v-select
        v-model="filters.urgency"
        :items="urgencies"
        label="Срочность"
        variant="outlined"
        density="compact"
        clearable
        @update:model-value="onFilterChange"
      ></v-select>
    </v-col>

    <!-- Фильтр по исполнителю -->
    <v-col cols="12" sm="6" md="2">
      <v-autocomplete
        v-model="filters.executor_id"
        :items="executors"
        item-title="name"
        item-value="id"
        label="Исполнитель"
        variant="outlined"
        density="compact"
        clearable
        @update:model-value="onFilterChange"
      ></v-autocomplete>
    </v-col>
  </v-row>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRequestStore } from '@/stores/requests'

const requestStore = useRequestStore()

const search = ref('')
const filters = ref({
  category: null,
  urgency: null,
  executor_id: null
})

const categories = computed(() => requestStore.categories)
const urgencies = ['Обычная', 'Средняя', 'Срочная', 'Критическая']
const executors = computed(() => requestStore.executors)

const onSearch = () => {
  requestStore.setSearch(search.value)
}

const onFilterChange = () => {
  requestStore.setFilters(filters.value)
}
</script>
```

### 3. Детальная карточка заявки (Модальное окно)

```vue
<template>
  <v-dialog
    v-model="dialog"
    max-width="900"
    scrollable
  >
    <v-card>
      <!-- Заголовок -->
      <v-card-title class="d-flex align-center">
        <span class="text-h6">
          Заявка #{{ request.request_number }}
        </span>
        <v-spacer></v-spacer>
        <v-chip :color="statusColor" label>
          {{ request.status }}
        </v-chip>
        <v-btn
          icon="mdi-close"
          variant="text"
          @click="dialog = false"
        ></v-btn>
      </v-card-title>

      <v-divider></v-divider>

      <!-- Вкладки -->
      <v-tabs v-model="tab">
        <v-tab value="info">Основное</v-tab>
        <v-tab value="comments">Комментарии ({{ commentsCount }})</v-tab>
        <v-tab value="history">История ({{ historyCount }})</v-tab>
        <v-tab value="media" v-if="hasMedia">Медиа ({{ mediaCount }})</v-tab>
      </v-tabs>

      <v-divider></v-divider>

      <!-- Содержимое вкладок -->
      <v-card-text style="height: 500px;">
        <v-window v-model="tab">
          <!-- Вкладка: Основное -->
          <v-window-item value="info">
            <v-row>
              <v-col cols="12" md="6">
                <v-list density="compact">
                  <v-list-item>
                    <template v-slot:prepend>
                      <v-icon>mdi-map-marker</v-icon>
                    </template>
                    <v-list-item-title>Адрес</v-list-item-title>
                    <v-list-item-subtitle>
                      {{ request.address }}
                    </v-list-item-subtitle>
                  </v-list-item>

                  <v-list-item>
                    <template v-slot:prepend>
                      <v-icon>mdi-tag</v-icon>
                    </template>
                    <v-list-item-title>Категория</v-list-item-title>
                    <v-list-item-subtitle>
                      {{ request.category }}
                    </v-list-item-subtitle>
                  </v-list-item>

                  <v-list-item>
                    <template v-slot:prepend>
                      <v-icon>mdi-alert</v-icon>
                    </template>
                    <v-list-item-title>Срочность</v-list-item-title>
                    <v-list-item-subtitle>
                      {{ request.urgency }}
                    </v-list-item-subtitle>
                  </v-list-item>
                </v-list>
              </v-col>

              <v-col cols="12" md="6">
                <v-list density="compact">
                  <v-list-item>
                    <template v-slot:prepend>
                      <v-icon>mdi-account</v-icon>
                    </template>
                    <v-list-item-title>Заявитель</v-list-item-title>
                    <v-list-item-subtitle>
                      {{ request.user.first_name }} {{ request.user.last_name }}
                    </v-list-item-subtitle>
                  </v-list-item>

                  <v-list-item v-if="request.executor">
                    <template v-slot:prepend>
                      <v-icon>mdi-account-wrench</v-icon>
                    </template>
                    <v-list-item-title>Исполнитель</v-list-item-title>
                    <v-list-item-subtitle>
                      {{ request.executor.first_name }} {{ request.executor.last_name }}
                    </v-list-item-subtitle>
                  </v-list-item>

                  <v-list-item>
                    <template v-slot:prepend>
                      <v-icon>mdi-calendar</v-icon>
                    </template>
                    <v-list-item-title>Создано</v-list-item-title>
                    <v-list-item-subtitle>
                      {{ formatDateTime(request.created_at) }}
                    </v-list-item-subtitle>
                  </v-list-item>
                </v-list>
              </v-col>

              <v-col cols="12">
                <v-card variant="outlined">
                  <v-card-title>Описание</v-card-title>
                  <v-card-text>
                    {{ request.description }}
                  </v-card-text>
                </v-card>
              </v-col>

              <!-- Медиа превью -->
              <v-col cols="12" v-if="hasMedia">
                <v-card variant="outlined">
                  <v-card-title>Фото и видео</v-card-title>
                  <v-card-text>
                    <v-row>
                      <v-col
                        v-for="(file, index) in request.media_files"
                        :key="index"
                        cols="6"
                        sm="4"
                        md="3"
                      >
                        <v-img
                          :src="getMediaUrl(file)"
                          aspect-ratio="1"
                          cover
                          class="cursor-pointer"
                          @click="openMedia(file)"
                        ></v-img>
                      </v-col>
                    </v-row>
                  </v-card-text>
                </v-card>
              </v-col>
            </v-row>
          </v-window-item>

          <!-- Вкладка: Комментарии -->
          <v-window-item value="comments">
            <comment-list :request-number="request.request_number"></comment-list>
          </v-window-item>

          <!-- Вкладка: История -->
          <v-window-item value="history">
            <history-timeline :request-number="request.request_number"></history-timeline>
          </v-window-item>

          <!-- Вкладка: Медиа -->
          <v-window-item value="media" v-if="hasMedia">
            <media-gallery :media-files="request.media_files"></media-gallery>
          </v-window-item>
        </v-window>
      </v-card-text>

      <v-divider></v-divider>

      <!-- Действия -->
      <v-card-actions>
        <v-btn
          color="primary"
          variant="text"
          prepend-icon="mdi-account-plus"
          @click="assignExecutor"
        >
          Назначить исполнителя
        </v-btn>

        <v-btn
          color="secondary"
          variant="text"
          prepend-icon="mdi-swap-horizontal"
          @click="changeStatus"
        >
          Сменить статус
        </v-btn>

        <v-spacer></v-spacer>

        <v-btn
          color="error"
          variant="text"
          prepend-icon="mdi-close-circle"
          @click="cancelRequest"
        >
          Отменить заявку
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref, computed } from 'vue'
import CommentList from '@/components/Comments/CommentList.vue'
import HistoryTimeline from '@/components/History/HistoryTimeline.vue'
import MediaGallery from '@/components/Media/MediaGallery.vue'

const props = defineProps({
  request: Object,
  modelValue: Boolean
})

const emit = defineEmits(['update:modelValue', 'assign', 'change-status', 'cancel'])

const dialog = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
})

const tab = ref('info')

const hasMedia = computed(() => props.request.media_files?.length > 0)
const mediaCount = computed(() => props.request.media_files?.length || 0)
const commentsCount = ref(0) // Получаем из API
const historyCount = ref(0) // Получаем из API

const statusColor = computed(() => {
  const colors = {
    'Новая': 'orange',
    'В работе': 'blue',
    'Закуп': 'purple',
    'Уточнение': 'deep-orange',
    'Выполнена': 'green',
    'Исполнено': 'cyan',
    'Принято': 'light-green',
    'Отменена': 'grey'
  }
  return colors[props.request.status] || 'grey'
})

const formatDateTime = (date) => {
  return new Date(date).toLocaleString('ru-RU')
}

const getMediaUrl = (fileId) => {
  return `/api/media/${fileId}`
}

const openMedia = (file) => {
  // Открыть медиа в полном размере
}

const assignExecutor = () => {
  emit('assign', props.request)
}

const changeStatus = () => {
  emit('change-status', props.request)
}

const cancelRequest = () => {
  emit('cancel', props.request)
}
</script>
```

### 4. Календарь смен

```vue
<template>
  <v-card>
    <v-card-title class="d-flex align-center">
      <v-btn
        icon="mdi-chevron-left"
        variant="text"
        @click="previousMonth"
      ></v-btn>

      <span class="mx-4">
        {{ currentMonthName }} {{ currentYear }}
      </span>

      <v-btn
        icon="mdi-chevron-right"
        variant="text"
        @click="nextMonth"
      ></v-btn>

      <v-spacer></v-spacer>

      <v-btn
        color="primary"
        prepend-icon="mdi-plus"
        @click="createShift"
      >
        Создать смену
      </v-btn>
    </v-card-title>

    <v-divider></v-divider>

    <v-card-text>
      <!-- Заголовки дней недели -->
      <v-row class="mb-2">
        <v-col
          v-for="day in weekDays"
          :key="day"
          class="text-center font-weight-bold"
        >
          {{ day }}
        </v-col>
      </v-row>

      <!-- Календарная сетка -->
      <v-row
        v-for="week in calendar"
        :key="week[0].date"
        class="calendar-week"
      >
        <v-col
          v-for="day in week"
          :key="day.date"
          class="calendar-day pa-2"
          :class="{
            'today': day.isToday,
            'other-month': !day.isCurrentMonth
          }"
        >
          <!-- Номер дня -->
          <div class="text-caption text-center mb-1">
            {{ day.day }}
          </div>

          <!-- Смены за день -->
          <div class="shifts-container">
            <v-chip
              v-for="shift in day.shifts"
              :key="shift.id"
              :color="getShiftColor(shift.status)"
              size="x-small"
              label
              class="mb-1"
              @click="openShift(shift)"
            >
              <v-icon size="x-small" start>
                {{ getShiftIcon(shift.status) }}
              </v-icon>
              {{ shift.executor_name }}
            </v-chip>

            <!-- Счетчик смен -->
            <v-chip
              v-if="day.shifts.length > 3"
              size="x-small"
              label
              color="grey"
            >
              +{{ day.shifts.length - 3 }}
            </v-chip>
          </div>
        </v-col>
      </v-row>
    </v-card-text>
  </v-card>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useShiftStore } from '@/stores/shifts'

const shiftStore = useShiftStore()

const currentMonth = ref(new Date().getMonth())
const currentYear = ref(new Date().getFullYear())

const weekDays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

const currentMonthName = computed(() => {
  const months = [
    'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
    'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
  ]
  return months[currentMonth.value]
})

const calendar = computed(() => {
  const year = currentYear.value
  const month = currentMonth.value

  // Первый день месяца
  const firstDay = new Date(year, month, 1)
  const firstDayOfWeek = (firstDay.getDay() + 6) % 7 // Понедельник = 0

  // Последний день месяца
  const lastDay = new Date(year, month + 1, 0)
  const daysInMonth = lastDay.getDate()

  // Создаем календарную сетку
  const weeks = []
  let currentWeek = []

  // Добавляем дни предыдущего месяца
  for (let i = firstDayOfWeek - 1; i >= 0; i--) {
    const date = new Date(year, month, -i)
    currentWeek.push(createDayObject(date, false))
  }

  // Добавляем дни текущего месяца
  for (let day = 1; day <= daysInMonth; day++) {
    const date = new Date(year, month, day)
    currentWeek.push(createDayObject(date, true))

    if (currentWeek.length === 7) {
      weeks.push(currentWeek)
      currentWeek = []
    }
  }

  // Добавляем дни следующего месяца
  if (currentWeek.length > 0) {
    for (let i = 1; currentWeek.length < 7; i++) {
      const date = new Date(year, month + 1, i)
      currentWeek.push(createDayObject(date, false))
    }
    weeks.push(currentWeek)
  }

  return weeks
})

const createDayObject = (date, isCurrentMonth) => {
  const dateString = date.toISOString().split('T')[0]
  const today = new Date().toISOString().split('T')[0]

  return {
    date: dateString,
    day: date.getDate(),
    isCurrentMonth,
    isToday: dateString === today,
    shifts: getShiftsForDate(dateString)
  }
}

const getShiftsForDate = (date) => {
  return shiftStore.getShiftsByDate(date)
}

const getShiftColor = (status) => {
  const colors = {
    'active': 'success',
    'planned': 'warning',
    'completed': 'grey'
  }
  return colors[status] || 'grey'
}

const getShiftIcon = (status) => {
  const icons = {
    'active': 'mdi-circle',
    'planned': 'mdi-circle-outline',
    'completed': 'mdi-check-circle'
  }
  return icons[status] || 'mdi-circle-outline'
}

const previousMonth = () => {
  if (currentMonth.value === 0) {
    currentMonth.value = 11
    currentYear.value--
  } else {
    currentMonth.value--
  }
  loadShifts()
}

const nextMonth = () => {
  if (currentMonth.value === 11) {
    currentMonth.value = 0
    currentYear.value++
  } else {
    currentMonth.value++
  }
  loadShifts()
}

const loadShifts = async () => {
  await shiftStore.fetchShifts(currentYear.value, currentMonth.value + 1)
}

const createShift = () => {
  // Открыть диалог создания смены
}

const openShift = (shift) => {
  // Открыть детали смены
}

onMounted(() => {
  loadShifts()
})
</script>

<style scoped>
.calendar-day {
  min-height: 100px;
  border: 1px solid rgba(0, 0, 0, 0.12);
}

.calendar-day.today {
  background-color: rgba(33, 150, 243, 0.1);
}

.calendar-day.other-month {
  opacity: 0.5;
}

.shifts-container {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
</style>
```

### 5. Дашборд менеджера

```vue
<template>
  <v-container fluid>
    <!-- Заголовок -->
    <v-row>
      <v-col cols="12">
        <h1 class="text-h4 mb-2">Дашборд менеджера</h1>
        <p class="text-subtitle-1 text-medium-emphasis">
          {{ currentDate }}
        </p>
      </v-col>
    </v-row>

    <!-- Статистика (карточки) -->
    <v-row>
      <!-- Заявки сегодня -->
      <v-col cols="12" sm="6" md="3">
        <v-card>
          <v-card-text>
            <div class="text-overline">Заявок сегодня</div>
            <div class="text-h3 text-primary">{{ stats.requests_today }}</div>
            <v-progress-linear
              :model-value="(stats.requests_completed / stats.requests_today) * 100"
              color="primary"
              class="mt-2"
            ></v-progress-linear>
            <div class="text-caption mt-1">
              Выполнено: {{ stats.requests_completed }} / {{ stats.requests_today }}
            </div>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- Исполнители -->
      <v-col cols="12" sm="6" md="3">
        <v-card>
          <v-card-text>
            <div class="text-overline">Исполнители</div>
            <div class="text-h3 text-success">{{ stats.executors_in_shift }}</div>
            <v-progress-linear
              :model-value="(stats.executors_in_shift / stats.executors_total) * 100"
              color="success"
              class="mt-2"
            ></v-progress-linear>
            <div class="text-caption mt-1">
              В смене: {{ stats.executors_in_shift }} / {{ stats.executors_total }}
            </div>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- Среднее время -->
      <v-col cols="12" sm="6" md="3">
        <v-card>
          <v-card-text>
            <div class="text-overline">Ср. время выполнения</div>
            <div class="text-h3 text-warning">{{ formatMinutes(stats.avg_completion_time) }}</div>
            <v-chip
              :color="stats.time_trend > 0 ? 'success' : 'error'"
              size="small"
              class="mt-2"
            >
              <v-icon start>
                {{ stats.time_trend > 0 ? 'mdi-trending-up' : 'mdi-trending-down' }}
              </v-icon>
              {{ Math.abs(stats.time_trend) }}%
            </v-chip>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- Эффективность -->
      <v-col cols="12" sm="6" md="3">
        <v-card>
          <v-card-text>
            <div class="text-overline">Эффективность</div>
            <div class="text-h3 text-info">{{ stats.efficiency }}%</div>
            <v-rating
              :model-value="stats.efficiency / 20"
              readonly
              size="small"
              class="mt-2"
              color="warning"
            ></v-rating>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Графики и таблицы -->
    <v-row>
      <!-- График заявок по часам -->
      <v-col cols="12" md="8">
        <v-card>
          <v-card-title>Заявки по часам</v-card-title>
          <v-card-text>
            <requests-chart :data="stats.hourly_requests"></requests-chart>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- Распределение по категориям -->
      <v-col cols="12" md="4">
        <v-card>
          <v-card-title>По категориям</v-card-title>
          <v-card-text>
            <category-pie-chart :data="stats.by_category"></category-pie-chart>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Топ исполнителей -->
    <v-row>
      <v-col cols="12">
        <v-card>
          <v-card-title>Топ-5 исполнителей</v-card-title>
          <v-data-table
            :headers="executorHeaders"
            :items="stats.top_executors"
            :items-per-page="5"
            hide-default-footer
          >
            <template v-slot:item.name="{ item }">
              <div class="d-flex align-center">
                <v-avatar size="32" class="mr-2">
                  <v-img :src="item.photo_url"></v-img>
                </v-avatar>
                <span>{{ item.name }}</span>
              </div>
            </template>

            <template v-slot:item.efficiency="{ item }">
              <v-chip :color="getEfficiencyColor(item.efficiency)">
                {{ item.efficiency }}%
              </v-chip>
            </template>

            <template v-slot:item.rating="{ item }">
              <v-rating
                :model-value="item.rating"
                readonly
                size="small"
                color="warning"
              ></v-rating>
            </template>
          </v-data-table>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAnalyticsStore } from '@/stores/analytics'
import RequestsChart from '@/components/Charts/RequestsChart.vue'
import CategoryPieChart from '@/components/Charts/CategoryPieChart.vue'

const analyticsStore = useAnalyticsStore()

const stats = computed(() => analyticsStore.dashboardStats)

const currentDate = computed(() => {
  return new Date().toLocaleDateString('ru-RU', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  })
})

const executorHeaders = [
  { title: 'Исполнитель', key: 'name', sortable: false },
  { title: 'Назначено', key: 'assigned', align: 'center' },
  { title: 'Выполнено', key: 'completed', align: 'center' },
  { title: 'Эффективность', key: 'efficiency', align: 'center' },
  { title: 'Рейтинг', key: 'rating', align: 'center' }
]

const formatMinutes = (minutes) => {
  const hours = Math.floor(minutes / 60)
  const mins = minutes % 60
  return `${hours}ч ${mins}м`
}

const getEfficiencyColor = (efficiency) => {
  if (efficiency >= 90) return 'success'
  if (efficiency >= 75) return 'warning'
  return 'error'
}

onMounted(async () => {
  await analyticsStore.fetchDashboardStats()
})
</script>
```

---

## 🏗️ ТЕХНИЧЕСКАЯ АРХИТЕКТУРА

### Общая архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                    TELEGRAM WEBAPP (Frontend)                │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Vue 3 + Vuetify 3 + Vite                              │ │
│  │  - Composition API                                      │ │
│  │  - Pinia (State Management)                            │ │
│  │  - Vue Router                                          │ │
│  │  - Socket.io-client (WebSocket)                       │ │
│  │  - Axios (HTTP Client)                                │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ HTTPS / WSS
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    FASTAPI BACKEND (Existing)                │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  NEW: Manager API Endpoints                            │ │
│  │  ├─ /api/manager/auth/telegram   (Auth)               │ │
│  │  ├─ /api/manager/dashboard       (Dashboard Stats)    │ │
│  │  ├─ /api/manager/kanban          (Kanban Board)       │ │
│  │  ├─ /api/manager/shifts          (Shifts Calendar)    │ │
│  │  ├─ /api/manager/assignments     (AI Assignments)     │ │
│  │  ├─ /api/manager/analytics       (Analytics & KPI)    │ │
│  │  └─ /ws/manager                  (WebSocket)          │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  EXISTING: Services (Reused)                           │ │
│  │  ├─ RequestService           ✅ (заявки)               │ │
│  │  ├─ ShiftService             ✅ (смены)                │ │
│  │  ├─ AssignmentService        ✅ (назначения)           │ │
│  │  ├─ SmartDispatcher          ✅ (ИИ-диспетчер)        │ │
│  │  ├─ AssignmentOptimizer      ✅ (оптимизатор)         │ │
│  │  ├─ GeoOptimizer             ✅ (гео-оптимизация)     │ │
│  │  ├─ ShiftAnalytics           ✅ (аналитика смен)      │ │
│  │  ├─ MetricsManager            ✅ (KPI метрики)         │ │
│  │  └─ NotificationService      ✅ (уведомления)         │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    DATABASE LAYER                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ PostgreSQL   │  │    Redis     │  │  Media       │      │
│  │ (Main DB)    │  │  (Cache)     │  │  Service     │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                 TELEGRAM BOT (Existing)                      │
│  - Handlers для всех ролей                                   │
│  - Получает уведомления от WebApp                           │
│  - Синхронизирует изменения в WebApp                        │
└─────────────────────────────────────────────────────────────┘
```

### Технологический стек

#### Frontend Stack
```yaml
Core:
  - Vue 3.4+ (Composition API, script setup)
  - Vuetify 3.5+ (Material Design 3)
  - Vite 5.x (Build tool)
  - TypeScript 5.x (опционально для production)

State Management:
  - Pinia 2.x (модульные stores)
  - Pinia Plugin Persist (localStorage sync)

HTTP & WebSocket:
  - Axios 1.x (REST API)
  - Socket.io-client 4.x (WebSocket для real-time)

Routing:
  - Vue Router 4.x (SPA routing)

UI Libraries:
  - Chart.js 4.x (графики и диаграммы)
  - VueUse 10.x (composition utilities)
  - Day.js 1.x (работа с датами)

Development:
  - Vite PWA Plugin (для Telegram WebApp)
  - ESLint + Prettier (code quality)
  - Vitest (unit testing, опционально)
```

#### Backend Stack
```yaml
Existing (Reused):
  - FastAPI 0.104+
  - SQLAlchemy 2.0
  - PostgreSQL 15
  - Redis 7
  - Aiogram 3.x (Telegram Bot)

New:
  - FastAPI WebSocket (для real-time)
  - python-socketio 5.x (Socket.IO сервер)
  - python-jose (JWT для WebApp auth)
```

---

## 🔄 ДВУСТОРОННЯЯ ИНТЕГРАЦИЯ

### Принцип работы

```
┌─────────────────┐                  ┌─────────────────┐
│  Telegram Bot   │ ◄──────────────► │  Manager WebApp │
└─────────────────┘                  └─────────────────┘
        │                                      │
        │                                      │
        ▼                                      ▼
┌────────────────────────────────────────────────────┐
│              Common Backend Services                │
│  - RequestService                                   │
│  - ShiftService                                    │
│  - NotificationService                             │
│  - WebSocket Event Bus                             │
└────────────────────────────────────────────────────┘
```

### Сценарии синхронизации

#### 1. Создание заявки в боте → видно в WebApp
```python
# Telegram Bot Handler
@router.message(CreateRequestStates.confirm)
async def create_request_handler(message: Message):
    # 1. Создаем заявку через RequestService
    request = request_service.create_request(...)

    # 2. Отправляем уведомление менеджеру в бот
    await notify_manager(request)

    # 3. Отправляем WebSocket событие
    await websocket_manager.broadcast({
        "type": "request.created",
        "data": request.to_dict()
    })

# WebApp получает обновление мгновенно
# через WebSocket connection
```

#### 2. Назначение исполнителя в WebApp → уведомление в бот
```python
# WebApp API Endpoint
@router.post("/api/manager/assignments/assign")
async def assign_executor(assignment_data: AssignmentCreate):
    # 1. Назначаем через AssignmentService
    assignment = assignment_service.assign_to_executor(...)

    # 2. Отправляем Telegram уведомление исполнителю
    await notification_service.notify_executor_assigned(
        executor_telegram_id=assignment.executor_id,
        request=assignment.request
    )

    # 3. Отправляем WebSocket событие всем менеджерам
    await websocket_manager.broadcast_to_managers({
        "type": "assignment.created",
        "data": assignment.to_dict()
    })

    return assignment
```

#### 3. Изменение статуса в боте → обновление в WebApp
```python
# Telegram Bot Handler
@router.callback_query(F.data.startswith("status_change:"))
async def status_change_handler(callback: CallbackQuery):
    # 1. Меняем статус через RequestService
    request = request_service.update_status(...)

    # 2. Логика уведомлений
    await notify_status_changed(request)

    # 3. WebSocket обновление для WebApp
    await websocket_manager.broadcast({
        "type": "request.status_changed",
        "data": {
            "request_number": request.request_number,
            "old_status": old_status,
            "new_status": request.status,
            "updated_at": datetime.now()
        }
    })
```

#### 4. Создание смены в WebApp → видно в боте
```python
# WebApp API Endpoint
@router.post("/api/manager/shifts/create")
async def create_shift(shift_data: ShiftCreate):
    # 1. Создаем смену через ShiftService
    shift = shift_service.create_shift(...)

    # 2. Telegram уведомление исполнителю
    await notification_service.notify_shift_created(
        executor_telegram_id=shift.user_id,
        shift=shift
    )

    # 3. WebSocket обновление
    await websocket_manager.broadcast_to_managers({
        "type": "shift.created",
        "data": shift.to_dict()
    })

    return shift
```

### WebSocket Event Bus

```python
# uk_management_bot/web/websocket_manager.py
from typing import Dict, Set, Callable
from fastapi import WebSocket
import logging

logger = logging.getLogger(__name__)

class WebSocketManager:
    """Управление WebSocket подключениями и broadcast событий"""

    def __init__(self):
        # Активные подключения: manager_telegram_id -> Set[WebSocket]
        self.active_connections: Dict[int, Set[WebSocket]] = {}

        # Подписки на события: event_type -> Set[callback]
        self.event_listeners: Dict[str, Set[Callable]] = {}

    async def connect(self, websocket: WebSocket, manager_id: int):
        """Подключение WebSocket клиента"""
        await websocket.accept()

        if manager_id not in self.active_connections:
            self.active_connections[manager_id] = set()

        self.active_connections[manager_id].add(websocket)
        logger.info(f"Manager {manager_id} connected via WebSocket")

    async def disconnect(self, websocket: WebSocket, manager_id: int):
        """Отключение WebSocket клиента"""
        if manager_id in self.active_connections:
            self.active_connections[manager_id].discard(websocket)

            if not self.active_connections[manager_id]:
                del self.active_connections[manager_id]

        logger.info(f"Manager {manager_id} disconnected from WebSocket")

    async def send_personal(self, manager_id: int, message: dict):
        """Отправка сообщения конкретному менеджеру"""
        if manager_id not in self.active_connections:
            logger.warning(f"Manager {manager_id} не подключен к WebSocket")
            return

        for websocket in self.active_connections[manager_id]:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения менеджеру {manager_id}: {e}")

    async def broadcast_to_managers(self, message: dict):
        """Broadcast сообщения всем подключенным менеджерам"""
        for manager_id, connections in self.active_connections.items():
            for websocket in connections:
                try:
                    await websocket.send_json(message)
                except Exception as e:
                    logger.error(f"Ошибка broadcast менеджеру {manager_id}: {e}")

    async def broadcast(self, message: dict):
        """Alias для broadcast_to_managers"""
        await self.broadcast_to_managers(message)

    def subscribe(self, event_type: str, callback: Callable):
        """Подписка на событие"""
        if event_type not in self.event_listeners:
            self.event_listeners[event_type] = set()

        self.event_listeners[event_type].add(callback)

    async def emit(self, event_type: str, data: dict):
        """Отправка события подписчикам"""
        if event_type in self.event_listeners:
            for callback in self.event_listeners[event_type]:
                try:
                    await callback(data)
                except Exception as e:
                    logger.error(f"Ошибка вызова callback для события {event_type}: {e}")

# Глобальный instance
websocket_manager = WebSocketManager()
```

### WebSocket Endpoint

```python
# uk_management_bot/web/api/manager/websocket.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from uk_management_bot.web.websocket_manager import websocket_manager
from uk_management_bot.web.api.manager.auth import get_current_manager
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.websocket("/ws/manager")
async def manager_websocket(
    websocket: WebSocket,
    token: str  # JWT token из query параметра
):
    """
    WebSocket endpoint для менеджера

    Подключение: ws://localhost:8000/ws/manager?token=JWT_TOKEN
    """
    try:
        # 1. Валидация JWT токена
        manager = await get_current_manager_from_token(token)

        if not manager:
            await websocket.close(code=4001, reason="Unauthorized")
            return

        # 2. Подключение к WebSocket
        await websocket_manager.connect(websocket, manager.id)

        # 3. Отправка приветственного сообщения
        await websocket.send_json({
            "type": "connected",
            "data": {
                "manager_id": manager.id,
                "manager_name": f"{manager.first_name} {manager.last_name}",
                "timestamp": datetime.now().isoformat()
            }
        })

        # 4. Обработка входящих сообщений
        try:
            while True:
                data = await websocket.receive_json()

                # Обрабатываем ping/pong для keep-alive
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue

                # Другие типы сообщений можно обработать здесь
                logger.debug(f"Получено сообщение от менеджера {manager.id}: {data}")

        except WebSocketDisconnect:
            logger.info(f"Менеджер {manager.id} отключился от WebSocket")

    except Exception as e:
        logger.error(f"Ошибка WebSocket для менеджера: {e}")

    finally:
        # 5. Отключение от WebSocket
        await websocket_manager.disconnect(websocket, manager.id)

async def get_current_manager_from_token(token: str):
    """Получение менеджера из JWT токена"""
    try:
        from uk_management_bot.web.api.manager.auth import verify_token
        payload = verify_token(token)

        # Получаем пользователя из БД
        from uk_management_bot.database.session import get_db
        db = next(get_db())

        from uk_management_bot.database.models.user import User
        manager = db.query(User).filter(
            User.id == payload["user_id"],
            User.roles.contains(["manager"])
        ).first()

        return manager
    except Exception as e:
        logger.error(f"Ошибка валидации токена: {e}")
        return None
```

### Frontend WebSocket Client

```typescript
// manager_webapp/src/services/websocket.ts
import { io, Socket } from 'socket.io-client'
import { useAuthStore } from '@/stores/auth'

class WebSocketService {
  private socket: Socket | null = null
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5

  connect() {
    const authStore = useAuthStore()
    const token = authStore.accessToken

    if (!token) {
      console.error('No access token for WebSocket connection')
      return
    }

    // Подключение к WebSocket
    this.socket = io('/ws/manager', {
      query: { token },
      transports: ['websocket'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionAttempts: this.maxReconnectAttempts
    })

    // Обработчики событий
    this.socket.on('connect', () => {
      console.log('WebSocket connected')
      this.reconnectAttempts = 0
    })

    this.socket.on('disconnect', (reason) => {
      console.log('WebSocket disconnected:', reason)
    })

    this.socket.on('error', (error) => {
      console.error('WebSocket error:', error)
    })

    // Обработка событий от сервера
    this.setupEventListeners()

    // Keep-alive ping каждые 30 секунд
    setInterval(() => {
      if (this.socket?.connected) {
        this.socket.emit('ping')
      }
    }, 30000)
  }

  private setupEventListeners() {
    if (!this.socket) return

    // Событие: Создана новая заявка
    this.socket.on('request.created', (data) => {
      const requestStore = useRequestStore()
      requestStore.addRequest(data)

      // Показываем уведомление
      showNotification('Новая заявка', `#${data.request_number}`)
    })

    // Событие: Изменен статус заявки
    this.socket.on('request.status_changed', (data) => {
      const requestStore = useRequestStore()
      requestStore.updateRequestStatus(data.request_number, data.new_status)
    })

    // Событие: Создано назначение
    this.socket.on('assignment.created', (data) => {
      const requestStore = useRequestStore()
      requestStore.updateRequestAssignment(data)
    })

    // Событие: Создана смена
    this.socket.on('shift.created', (data) => {
      const shiftStore = useShiftStore()
      shiftStore.addShift(data)
    })

    // Событие: Смена началась
    this.socket.on('shift.started', (data) => {
      const shiftStore = useShiftStore()
      shiftStore.updateShiftStatus(data.shift_id, 'active')
    })

    // Событие: Смена завершена
    this.socket.on('shift.ended', (data) => {
      const shiftStore = useShiftStore()
      shiftStore.updateShiftStatus(data.shift_id, 'completed')
    })
  }

  disconnect() {
    if (this.socket) {
      this.socket.disconnect()
      this.socket = null
    }
  }

  emit(event: string, data: any) {
    if (this.socket?.connected) {
      this.socket.emit(event, data)
    }
  }
}

export const websocketService = new WebSocketService()
```

---

## 📁 СТРУКТУРА ПРОЕКТА

### Backend структура

```
uk_management_bot/
├── web/
│   ├── __init__.py
│   ├── main.py                      # ОБНОВИТЬ: добавить manager routes
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── invite.py                # ✅ СУЩЕСТВУЕТ
│   │   │
│   │   └── manager/                 # 🆕 НОВОЕ
│   │       ├── __init__.py
│   │       ├── auth.py              # Telegram WebApp auth
│   │       ├── dashboard.py         # Dashboard stats
│   │       ├── requests.py          # Kanban API
│   │       ├── shifts.py            # Shifts calendar API
│   │       ├── assignments.py       # AI assignments API
│   │       ├── analytics.py         # Analytics & KPI API
│   │       └── websocket.py         # WebSocket endpoint
│   │
│   ├── templates/
│   │   ├── home.html                # ✅ СУЩЕСТВУЕТ
│   │   ├── register.html            # ✅ СУЩЕСТВУЕТ
│   │   │
│   │   └── manager/                 # 🆕 НОВОЕ
│   │       └── index.html           # Vue.js app entry point
│   │
│   ├── static/                      # 🆕 НОВОЕ
│   │   └── manager/                 # Built Vue.js app files
│   │       ├── assets/
│   │       ├── css/
│   │       └── js/
│   │
│   └── websocket_manager.py         # 🆕 НОВОЕ: WebSocket manager
│
├── services/                         # ✅ ВСЕ СУЩЕСТВУЮТ - ИСПОЛЬЗУЕМ
│   ├── request_service.py
│   ├── shift_service.py
│   ├── assignment_service.py
│   ├── smart_dispatcher.py
│   ├── assignment_optimizer.py
│   ├── geo_optimizer.py
│   ├── shift_analytics.py
│   ├── metrics_manager.py
│   ├── recommendation_engine.py
│   └── notification_service.py
│
└── database/
    └── models/                       # ✅ ВСЕ СУЩЕСТВУЮТ
        ├── user.py
        ├── request.py
        ├── shift.py
        ├── request_assignment.py
        └── ...
```

### Frontend структура

```
manager_webapp/                       # 🆕 НОВЫЙ ПРОЕКТ
├── public/
│   └── favicon.ico
│
├── src/
│   ├── main.ts                       # Vue app entry
│   ├── App.vue                       # Root component
│   │
│   ├── router/
│   │   └── index.ts                  # Vue Router config
│   │
│   ├── stores/                       # Pinia stores
│   │   ├── auth.ts                   # Authentication store
│   │   ├── requests.ts               # Requests/Kanban store
│   │   ├── shifts.ts                 # Shifts store
│   │   ├── analytics.ts              # Analytics store
│   │   └── websocket.ts              # WebSocket store
│   │
│   ├── services/
│   │   ├── api.ts                    # Axios instance
│   │   ├── websocket.ts              # WebSocket service
│   │   └── telegram.ts               # Telegram WebApp API
│   │
│   ├── views/                        # Page components
│   │   ├── Dashboard.vue
│   │   ├── Kanban.vue
│   │   ├── Shifts.vue
│   │   ├── Analytics.vue
│   │   └── Settings.vue
│   │
│   ├── components/
│   │   ├── Dashboard/
│   │   │   ├── StatsCard.vue
│   │   │   ├── RequestsChart.vue
│   │   │   └── CategoryPieChart.vue
│   │   │
│   │   ├── Kanban/
│   │   │   ├── KanbanBoard.vue
│   │   │   ├── KanbanColumn.vue
│   │   │   ├── RequestCard.vue
│   │   │   └── RequestDetailsDialog.vue
│   │   │
│   │   ├── Shifts/
│   │   │   ├── ShiftCalendar.vue
│   │   │   ├── ShiftDetailsDialog.vue
│   │   │   └── CreateShiftDialog.vue
│   │   │
│   │   ├── Assignments/
│   │   │   ├── AssignExecutorDialog.vue
│   │   │   └── AIRecommendations.vue
│   │   │
│   │   ├── Comments/
│   │   │   └── CommentList.vue
│   │   │
│   │   ├── History/
│   │   │   └── HistoryTimeline.vue
│   │   │
│   │   ├── Media/
│   │   │   └── MediaGallery.vue
│   │   │
│   │   ├── Charts/
│   │   │   ├── LineChart.vue
│   │   │   └── PieChart.vue
│   │   │
│   │   └── Shared/
│   │       ├── AppBar.vue
│   │       ├── NavigationDrawer.vue
│   │       └── LoadingSpinner.vue
│   │
│   ├── types/                        # TypeScript types
│   │   ├── request.ts
│   │   ├── shift.ts
│   │   ├── user.ts
│   │   └── api.ts
│   │
│   ├── utils/
│   │   ├── formatters.ts             # Date, time formatters
│   │   ├── validators.ts             # Input validation
│   │   └── constants.ts              # App constants
│   │
│   └── assets/
│       ├── styles/
│       │   └── main.scss
│       └── images/
│
├── index.html
├── vite.config.ts
├── package.json
├── tsconfig.json
└── .env
```

---

## 📅 ПЛАН РАЗРАБОТКИ

### Общий Timeline: 3 недели (15 рабочих дней)

```
Неделя 1: Backend API + Интеграция (5 дней)
├─ День 1-2: API endpoints
├─ День 3: WebSocket setup
└─ День 4-5: Тестирование интеграции

Неделя 2: Frontend Development (5 дней)
├─ День 1: Setup + Dashboard
├─ День 2-3: Kanban Board
├─ День 4: Shifts Calendar
└─ День 5: Интеграция с WebSocket

Неделя 3: Polishing + Deploy (5 дней)
├─ День 1-2: UI/UX improvements
├─ День 3: Тестирование
├─ День 4: Документация
└─ День 5: Production deploy
```

### Детальная декомпозиция: 36 задач

#### ФАЗА 1: Backend API (Неделя 1)

**День 1: Authentication & Core Setup (4 задачи)**
```
✅ Задача 1.1: Telegram WebApp Auth endpoint
   - POST /api/manager/auth/telegram
   - Валидация initData
   - Генерация JWT токенов
   Файлы: uk_management_bot/web/api/manager/auth.py
   Время: 3 часа

✅ Задача 1.2: JWT middleware
   - Dependency для проверки токена
   - get_current_manager() функция
   Файлы: uk_management_bot/web/api/manager/auth.py
   Время: 2 часа

✅ Задача 1.3: WebSocket Manager
   - Класс для управления подключениями
   - Broadcast функции
   Файлы: uk_management_bot/web/websocket_manager.py
   Время: 2 часа

✅ Задача 1.4: WebSocket Endpoint
   - /ws/manager endpoint
   - Connection handling
   Файлы: uk_management_bot/web/api/manager/websocket.py
   Время: 1 час
```

**День 2: Dashboard & Requests API (5 задач)**
```
✅ Задача 2.1: Dashboard Stats API
   - GET /api/manager/dashboard
   - Интеграция с MetricsManager
   Файлы: uk_management_bot/web/api/manager/dashboard.py
   Время: 3 часа

✅ Задача 2.2: Kanban Board API
   - GET /api/manager/kanban
   - Фильтрация и сортировка
   Файлы: uk_management_bot/web/api/manager/requests.py
   Время: 3 часа

✅ Задача 2.3: Request Details API
   - GET /api/manager/requests/{number}
   - Включить comments, history, media
   Файлы: uk_management_bot/web/api/manager/requests.py
   Время: 2 часа
```

**День 3: Shifts & Assignments API (5 задач)**
```
✅ Задача 3.1: Shifts Calendar API
   - GET /api/manager/shifts/calendar
   - Группировка по датам
   Файлы: uk_management_bot/web/api/manager/shifts.py
   Время: 2 часа

✅ Задача 3.2: Create Shift API
   - POST /api/manager/shifts/create
   - Интеграция с ShiftService
   Файлы: uk_management_bot/web/api/manager/shifts.py
   Время: 2 часа

✅ Задача 3.3: AI Assignment API
   - POST /api/manager/assignments/ai-assign
   - Интеграция с SmartDispatcher
   Файлы: uk_management_bot/web/api/manager/assignments.py
   Время: 3 часа

✅ Задача 3.4: Manual Assignment API
   - POST /api/manager/assignments/assign
   - POST /api/manager/assignments/bulk-assign
   Файлы: uk_management_bot/web/api/manager/assignments.py
   Время: 1 час
```

**День 4-5: Analytics & Integration (6 задач)**
```
✅ Задача 4.1: Analytics API
   - GET /api/manager/analytics
   - Интеграция с ShiftAnalytics
   Файлы: uk_management_bot/web/api/manager/analytics.py
   Время: 3 часа

✅ Задача 4.2: WebSocket Events Integration
   - RequestService → WebSocket broadcast
   - ShiftService → WebSocket broadcast
   Файлы: uk_management_bot/services/request_service.py
            uk_management_bot/services/shift_service.py
   Время: 4 часа

✅ Задача 4.3: Telegram Bot → WebApp notifications
   - Обновление handlers для WebSocket emit
   Файлы: uk_management_bot/handlers/requests.py
            uk_management_bot/handlers/shifts.py
   Время: 3 часа

✅ Задача 4.4: API Testing
   - Pytest для всех endpoints
   Файлы: tests/web/test_manager_api.py
   Время: 4 часа

✅ Задача 4.5: OpenAPI Documentation
   - Swagger docs
   Файлы: uk_management_bot/web/main.py
   Время: 1 час

✅ Задача 4.6: Docker Integration
   - Обновить docker-compose.dev.yml
   Файлы: docker-compose.dev.yml
   Время: 1 час
```

#### ФАЗА 2: Frontend Development (Неделя 2)

**День 1: Project Setup + Dashboard (4 задачи)**
```
✅ Задача 5.1: Vue 3 + Vite Setup
   - npm create vite@latest
   - Vuetify 3 setup
   - Vue Router setup
   Файлы: manager_webapp/package.json
            manager_webapp/vite.config.ts
   Время: 2 часа

✅ Задача 5.2: Pinia Stores Setup
   - auth.ts
   - requests.ts
   - shifts.ts
   - analytics.ts
   Файлы: manager_webapp/src/stores/
   Время: 2 часа

✅ Задача 5.3: API Service
   - Axios instance
   - JWT interceptors
   Файлы: manager_webapp/src/services/api.ts
   Время: 1 час

✅ Задача 5.4: Telegram WebApp Integration
   - initData получение
   - Authentication flow
   Файлы: manager_webapp/src/services/telegram.ts
            manager_webapp/src/stores/auth.ts
   Время: 3 часа

✅ Задача 5.5: Dashboard View
   - Stats cards
   - Basic layout
   Файлы: manager_webapp/src/views/Dashboard.vue
   Время: 4 часа
```

**День 2-3: Kanban Board (6 задач)**
```
✅ Задача 6.1: Kanban Board Component
   - Column layout
   - Scrollable columns
   Файлы: manager_webapp/src/components/Kanban/KanbanBoard.vue
   Время: 3 часа

✅ Задача 6.2: Request Card Component
   - Карточка заявки
   - Color coding
   Файлы: manager_webapp/src/components/Kanban/RequestCard.vue
   Время: 2 часа

✅ Задача 6.3: Filters & Search
   - Filter component
   - Search functionality
   Файлы: manager_webapp/src/components/Kanban/KanbanBoard.vue
   Время: 2 часа

✅ Задача 6.4: Request Details Dialog
   - Modal window
   - Tabs (info, comments, history, media)
   Файлы: manager_webapp/src/components/Kanban/RequestDetailsDialog.vue
   Время: 4 часа

✅ Задача 6.5: Assignment Dialog
   - Assign executor
   - AI recommendations
   Файлы: manager_webapp/src/components/Assignments/AssignExecutorDialog.vue
   Время: 3 часа

✅ Задача 6.6: Status Change Logic
   - Status dropdown
   - API integration
   Файлы: manager_webapp/src/stores/requests.ts
   Время: 2 часа
```

**День 4: Shifts Calendar (4 задачи)**
```
✅ Задача 7.1: Calendar Grid Component
   - Month view
   - Day cells
   Файлы: manager_webapp/src/components/Shifts/ShiftCalendar.vue
   Время: 4 часа

✅ Задача 7.2: Shift Chips
   - Visual representation
   - Status colors
   Файлы: manager_webapp/src/components/Shifts/ShiftCalendar.vue
   Время: 2 часа

✅ Задача 7.3: Create Shift Dialog
   - Form для создания смены
   - Executor selection
   Файлы: manager_webapp/src/components/Shifts/CreateShiftDialog.vue
   Время: 3 часа

✅ Задача 7.4: Shift Details Dialog
   - Modal с деталями смены
   Файлы: manager_webapp/src/components/Shifts/ShiftDetailsDialog.vue
   Время: 2 часа
```

**День 5: WebSocket Integration (3 задачи)**
```
✅ Задача 8.1: WebSocket Service
   - Socket.io-client setup
   - Connection management
   Файлы: manager_webapp/src/services/websocket.ts
   Время: 3 часа

✅ Задача 8.2: WebSocket Store
   - Event listeners
   - Store updates
   Файлы: manager_webapp/src/stores/websocket.ts
   Время: 2 часа

✅ Задача 8.3: Real-time Updates
   - Интеграция с requests store
   - Интеграция с shifts store
   Файлы: manager_webapp/src/stores/requests.ts
            manager_webapp/src/stores/shifts.ts
   Время: 3 часа
```

#### ФАЗА 3: Polishing & Deploy (Неделя 3)

**День 1-2: UI/UX Improvements (5 задач)**
```
✅ Задача 9.1: Charts Integration
   - Chart.js setup
   - Line charts
   - Pie charts
   Файлы: manager_webapp/src/components/Charts/
   Время: 4 часа

✅ Задача 9.2: Loading States
   - Skeleton loaders
   - Progress indicators
   Файлы: manager_webapp/src/components/Shared/
   Время: 2 часа

✅ Задача 9.3: Error Handling
   - Error boundaries
   - Toast notifications
   Файлы: manager_webapp/src/utils/
   Время: 2 часа

✅ Задача 9.4: Responsive Design
   - Mobile optimization
   - Tablet optimization
   Файлы: manager_webapp/src/assets/styles/
   Время: 4 часа

✅ Задача 9.5: Telegram WebApp Theme
   - Dark/Light theme sync
   - Telegram colors
   Файлы: manager_webapp/src/plugins/vuetify.ts
   Время: 2 часа
```

**День 3: Testing (3 задачи)**
```
✅ Задача 10.1: Manual Testing
   - Все функции
   - Все сценарии
   Время: 4 часа

✅ Задача 10.2: Integration Testing
   - Bot ↔ WebApp sync
   - Real-time updates
   Время: 3 часа

✅ Задача 10.3: Performance Testing
   - Load testing
   - WebSocket stability
   Время: 1 час
```

**День 4: Documentation (2 задачи)**
```
✅ Задача 11.1: User Guide
   - Инструкция для менеджеров
   Файлы: docs/MANAGER_WEBAPP_USER_GUIDE.md
   Время: 3 часа

✅ Задача 11.2: Developer Documentation
   - API документация
   - Deployment guide
   Файлы: docs/MANAGER_WEBAPP_DEV_GUIDE.md
   Время: 3 часа
```

**День 5: Production Deploy (3 задачи)**
```
✅ Задача 12.1: Production Build
   - Vite build
   - Оптимизация bundle
   Файлы: manager_webapp/dist/
   Время: 1 час

✅ Задача 12.2: Deploy to Server
   - Docker deployment
   - Nginx configuration
   Файлы: docker-compose.prod.yml
   Время: 3 часа

✅ Задача 12.3: Production Testing
   - Smoke tests
   - User acceptance testing
   Время: 2 часа
```

---

## 📊 ОЦЕНКА РЕСУРСОВ

### Временные затраты

| Фаза | Задач | Дней | Часов |
|------|-------|------|-------|
| Фаза 1: Backend API | 16 | 5 | 40 |
| Фаза 2: Frontend | 17 | 5 | 40 |
| Фаза 3: Polishing & Deploy | 13 | 5 | 40 |
| **ИТОГО** | **36** | **15** | **120** |

### Технические требования

#### Development
```yaml
Hardware:
  - MacBook / Desktop PC
  - 8GB RAM минимум
  - 20GB свободного места

Software:
  - Docker Desktop
  - Node.js 20+
  - Python 3.11+
  - VS Code (рекомендуется)
```

#### Production
```yaml
Server:
  - VPS: 2 CPU, 4GB RAM
  - Ubuntu 22.04 LTS
  - Docker + Docker Compose

Domain:
  - HTTPS обязателен для Telegram WebApp
  - SSL сертификат (Let's Encrypt)

Monitoring:
  - Logs (Docker logs)
  - Sentry (опционально)
```

### Стоимость (месячная)

| Компонент | Стоимость |
|-----------|-----------|
| VPS (4GB RAM, 2 CPU) | $20-40/мес |
| SSL сертификат | $0 (Let's Encrypt) |
| Monitoring (Sentry) | $0-26/мес |
| **ИТОГО** | **$20-66/мес** |

---

## ✅ КРИТЕРИИ УСПЕХА

### Функциональные
- [x] Менеджер может видеть все заявки на канбан-доске
- [x] Менеджер может фильтровать и искать заявки
- [x] Менеджер может назначать исполнителей (вручную и через ИИ)
- [x] Менеджер может управлять сменами через календарь
- [x] Менеджер видит аналитику и KPI
- [x] Система обновляется в реальном времени (WebSocket)
- [x] Все изменения видны и в WebApp, и в боте (двусторонняя синхронизация)

### Технические
- [x] API response time < 500ms (95 percentile)
- [x] WebSocket latency < 100ms
- [x] Frontend bundle size < 500KB (gzipped)
- [x] Lighthouse score > 85 (Performance)
- [x] Работает в Telegram Desktop и Mobile
- [x] Адаптивный дизайн для всех устройств

### UX
- [x] Интуитивно понятный интерфейс
- [x] Время загрузки < 3 секунды
- [x] Responsive на планшетах и ПК
- [x] Telegram theme integration

---

## 🎓 ЗАКЛЮЧЕНИЕ

### Итоговая рекомендация

**Telegram WebApp** является оптимальным решением для данного проекта:

✅ **Быстрый запуск** - 3 недели вместо 8 недель
✅ **Низкие затраты** - использует существующую инфраструктуру
✅ **Нативная интеграция** - работает внутри Telegram
✅ **Двусторонняя синхронизация** - полная интеграция с ботом
✅ **Real-time обновления** - WebSocket для мгновенной синхронизации
✅ **AI-powered** - интеграция с существующими ИИ-сервисами

### Ожидаемые результаты

**После 3 недель разработки**:
- 📊 Полнофункциональный дашборд с KPI
- 📋 Визуальная канбан-доска заявок
- 📅 Календарь смен с управлением
- 🤖 ИИ-назначения одним кликом
- ⚡ Real-time синхронизация с ботом
- 📱 Адаптивный дизайн для всех устройств

### Следующие шаги

1. **✅ Утверждение ТЗ** - согласовать с заказчиком
2. **🚀 Start Development** - начать Фазу 1
3. **📊 Weekly Updates** - отчеты о прогрессе
4. **🧪 Testing** - непрерывное тестирование
5. **🎉 Launch** - production deploy

---

**Документ подготовлен**: 19 октября 2025
**Автор**: Claude Code (Sonnet 4.5)
**Версия**: 2.0.0 (Оптимизировано под Telegram WebApp)
**Статус**: ✅ Готово к реализации

---

## 📎 REFERENCES

1. [Vue 3 Documentation](https://vuejs.org/) - Context7: `/vuejs/docs`
2. [Vuetify 3 Documentation](https://vuetifyjs.com/) - Context7: `/vuetifyjs/vuetify`
3. [FastAPI WebSocket](https://fastapi.tiangolo.com/) - Context7: `/fastapi/fastapi`
4. [Telegram WebApp Documentation](https://core.telegram.org/bots/webapps)
5. [UK Management Bot - CLAUDE.md](CLAUDE.md)
6. [Microservices Architecture](MemoryBank/MICROSERVICES_ARCHITECTURE.md)
