# Local NASA data and cache

Raw data and generated outputs are git-ignored. No secrets belong here. Real NASA
FIRMS, POWER, fire/cloud masks, land-cover, terrain and GEOS data were acquired in
this workspace; see ../README.md and ../docs/sources.md for exact reproduction.
Original files/subsets retain source URL, download timestamp, size and SHA256
manifests. Copy complete raw caches and manifests together for offline processing.
Never invent missing coverage or replace a quarantined detection with a negative.
The small fixture is synthetic and explicitly separate from real-data model evidence.

Inactive S-NPP originals are retained in both `gridded-fire/packed-raw/` and
`gridded-fire/packed-originals/`. Original NOAA-20 files are retained in
`gridded-noaa20/packed-originals/`. Every archive and original member was hashed and
verified before removing its unpacked duplicate. Use the three restore commands
in the main forecasting README and allow enough disk space before rerunning the
original daily-file adapters. New global/Greek scientific subsets remain separately
audited. Never remove `/workspace/work/torch-cache` while the optional research
environment uses its space-saving package symlinks; it is software, not NASA data.
