@echo off
set DATABASE_URL=postgresql://reliefos:reliefos@localhost:5433/reliefos
cd /d D:\RescueOS\RescueOS
python -m scripts.ingest.osm_pbf > D:\RescueOS\RescueOS\osm_ingest.log 2>&1
echo EXIT_CODE=%ERRORLEVEL% >> D:\RescueOS\RescueOS\osm_ingest.log
