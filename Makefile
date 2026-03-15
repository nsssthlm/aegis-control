.PHONY: dev stop logs test smoke demo-alert demo-presence voice-test build clean install

install:
	pip3 install -r requirements.txt
	docker compose build

dev:
	docker compose up -d
	honcho start
	# honcho blockerar — Ctrl+C stoppar alla processer

stop:
	docker compose down
	honcho stop 2>/dev/null || true

logs:
	honcho start 2>&1 | tee aegis.log

test:
	python3 -m pytest orion-hub/tests/ -v

smoke:
	@bash scripts/smoke_test.sh

demo-alert:
	@bash scripts/demo_alert.sh

demo-presence:
	@bash scripts/demo_presence.sh

voice-test:
	@curl -s -X POST http://localhost:8002/speak \
	  -H "Content-Type: application/json" \
	  -d '{"text":"AEGIS Control online. Voice system nominal. Ready for operations.","priority":10}'
	@echo "Voice test sent."

clean:
	docker compose down -v
	rm -f aegis.db
	rm -rf /tmp/aegis-voice/
