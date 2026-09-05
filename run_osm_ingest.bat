@echo off
setlocal
cd /d "%~dp0"
set DATABASE_URL=postgresql://reliefos:reliefos@localhost:5433/reliefos
python -m scripts.ingest.osm_pbf > D:\RescueOS\RescueOS\osm_ingest.log 2>&1
echo EXIT_CODE=%ERRORLEVEL% >> D:\RescueOS\RescueOS\osm_ingest.log
