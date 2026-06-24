.PHONY: install scrape-my scrape-all dashboard run clean help

# Загрузить .env если есть
ifneq (,$(wildcard .env))
  include .env
  export
endif

MY_USER_ID  ?= 1382
SCRAPE_COUNT?= 10000
LAST_MATCH_ID?= 591399
DB_PATH     ?= data/players.db
HTML_OUT    ?= data/stats.html

help:
	@echo ""
	@echo "  make install       — создать venv и установить зависимости"
	@echo "  make scrape-my     — собрать свои игры (быстро, ~5 мин)"
	@echo "  make scrape-all    — собрать все матчи (долго)"
	@echo "  make dashboard     — сгенерировать HTML дашборд"
	@echo "  make run           — scrape-my + dashboard"
	@echo "  make clean         — удалить базу и HTML"
	@echo ""

install:
	python3 -m venv venv
	venv/bin/pip install --upgrade pip
	venv/bin/pip install -r requirements.txt
	mkdir -p data
	@echo ""
	@echo "✓ Готово. Скопируй .env.example в .env и заполни MY_USER_ID"
	@echo "  cp .env.example .env"

scrape-my:
	mkdir -p data
	venv/bin/python scraper.py --mode my --user-id $(MY_USER_ID) --db $(DB_PATH)

scrape-all:
	mkdir -p data
	venv/bin/python scraper.py --mode all --last $(LAST_MATCH_ID) --count $(SCRAPE_COUNT) --db $(DB_PATH)

dashboard:
	venv/bin/python dashboard.py --db $(DB_PATH) --user-id $(MY_USER_ID) --out $(HTML_OUT)
	@echo "Открой: $(HTML_OUT)"

run: scrape-my dashboard

clean:
	rm -f $(DB_PATH) $(HTML_OUT)
	@echo "Очищено"
