```commandline
docker build --tag telegram_antispam:latest .
docker run -e TOKEN="<your bot token here>" -e DATA_PATH="/data/data" --restart=always -v $(pwd)/data:/data telegram_antispam:latest
```
