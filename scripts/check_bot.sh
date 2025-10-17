#!/bin/bash
# Bot health check script
if ! systemctl is-active --quiet batch27-bot; then
    echo "$(date): Bot is down! Attempting restart..." >> /home/ubuntu/batch27-bot/health_check.log
    systemctl restart batch27-bot
else
    echo "$(date): Bot is running" >> /home/ubuntu/batch27-bot/health_check.log
fi
