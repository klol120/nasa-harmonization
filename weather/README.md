# weather/

Mounted into the api container at `/data/weather`. On start the container loads any `<region>.json` here, then fetches only the months that are still missing from Meteomatics.

Use it to move the fetched weather to another machine (the hosting server, or a teammate) without spending Meteomatics requests again, or to keep the data after the account ends on 2026-11-22:

```sh
docker compose exec api python -m firecal_api.cli weather-export /data/weather   # writes weather/<region>.json
# copy the files to the other machine's weather/ folder, then:
docker compose up -d
```

The `.json` files are git-ignored. Check Meteomatics' data terms before publishing them in a public repo.
