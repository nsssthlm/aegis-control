#!/bin/bash
TS=$(python3 -c "import time; print(int(time.time()))")
curl -s -X POST http://localhost:8001/api/webhook \
  -H "Content-Type: application/json" \
  -d "{
    \"alarm\": {
      \"name\":\"AEGIS Demo\",
      \"sources\":[{\"device\":\"AABBCCDDEEFF\",\"type\":\"include\"}],
      \"triggers\":[{\"key\":\"person\",\"device\":\"AABBCCDDEEFF\"}]
    },
    \"timestamp\":$TS
  }" > /dev/null
echo "Demo presence event sent — check UI and listen for voice."
