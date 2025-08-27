#!/bin/bash

# Run Django live_update management command every 5 minutes
echo "Starting live update scheduler - running every 5 minutes"
echo "Press Ctrl+C to stop"

while true; do
    echo "$(date): Running live_update..."
    django-admin live_update
    
    if [ $? -eq 0 ]; then
        echo "$(date): live_update completed successfully"
    else
        echo "$(date): live_update failed with exit code $?"
    fi
    
    echo "$(date): Waiting 5 minutes before next run..."
    sleep 300  # 300 seconds = 5 minutes
done
