#!/bin/bash
ID="demo-$(date +%s)"
curl -s -X POST http://localhost:8001/api/internal/event \
  -H "Content-Type: application/json" \
  -d "{
    \"id\":\"$ID\",
    \"type\":\"WAZUH\",
    \"severity\":\"CRITICAL\",
    \"source\":\"CV-DC05\",
    \"env\":\"CEDERVALL\",
    \"title\":\"Brute force attack detected — 47 failed attempts\",
    \"body\":\"Source IP: 185.220.101.45 | Target: Administrator | EventID: 4625\",
    \"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",
    \"speak\":true,
    \"metadata\":{\"rule_level\":14,\"attack_ip\":\"185.220.101.45\"}
  }" > /dev/null
echo "Demo alert injected — check UI and listen for voice."
