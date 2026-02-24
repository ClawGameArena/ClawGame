#!/bin/bash
cd /root/clawgame/api
source venv/bin/activate
python main.py > /tmp/clawgame-api.log 2>&1
