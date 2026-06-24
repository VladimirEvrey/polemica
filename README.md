# Polemica Stats

Автоматический сбор статистики с [polemicagame.com](https://polemicagame.com) и публикация на GitHub Pages.

## Структура

```
polemica/
├── scraper.py                      — сбор данных
├── dashboard.py                    — генерация HTML
├── requirements.txt
├── .env.example                    — шаблон конфига
├── Makefile                        — локальный запуск
├── .github/
│   └── workflows/
│       └── scrape.yml              — автозапуск по расписанию
└── data/                           — база и HTML (в .gitignore)
```

## Локальный запуск

```bash
make install          # создать venv + зависимости
cp .env.example .env  # заполнить MY_USER_ID
make run              # собрать данные + сгенерировать HTML
```

## Настройка GitHub Actions + Pages

### 1. Создай репо на GitHub и запушь код

```bash
git init
git add .
git commit -m "init"
git remote add origin https://github.com/ВАШ_ЮЗЕР/polemica.git
git push -u origin main
```

### 2. Добавь секреты

Открой репо → **Settings → Secrets and variables → Actions → New repository secret**

| Секрет | Значение |
|---|---|
| `MY_USER_ID` | Твой ID на polemicagame.com (например `1382`) |
| `LAST_MATCH_ID` | Последний известный матч (например `591399`) |

### 3. Включи GitHub Pages

Открой репо → **Settings → Pages**
- Source: **GitHub Actions**
- Сохрани

### 4. Запусти вручную (первый раз)

Открой репо → **Actions → Scrape & Publish Stats → Run workflow**

После успешного запуска страница будет доступна по адресу:
```
https://ВАШ_ЮЗЕР.github.io/polemica/
```

### 5. Автозапуск

Workflow запускается **каждый день в 6:00 UTC** автоматически.  
Можно изменить расписание в `.github/workflows/scrape.yml`:

```yaml
# Каждые 6 часов:
- cron: "0 */6 * * *"

# Каждый понедельник в 9:00:
- cron: "0 9 * * 1"
```

## Как найти свой user_id

Зайди на профиль → число в URL:  
`polemicagame.com/profile/1382` → `MY_USER_ID=1382`
