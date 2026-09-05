@echo off
setlocal
cd /d "%~dp0"

echo Starting ReliefOS PostGIS database...
docker inspect reliefos-postgis >nul 2>&1
if not errorlevel 1 (
	docker start reliefos-postgis >nul 2>&1
) else (
	docker compose up -d --wait
	if errorlevel 1 (
		echo.
		echo ERROR: PostGIS could not be started. Make sure Docker Desktop is running.
		exit /b 1
	)
)

set "DATABASE_URL=postgresql://reliefos:reliefos@localhost:5433/reliefos"

for /l %%I in (1,1,30) do (
	docker exec reliefos-postgis pg_isready -U reliefos -d reliefos >nul 2>&1
	if not errorlevel 1 goto database_ready
	timeout /t 1 /nobreak >nul
)
echo.
echo ERROR: PostGIS did not become ready within 30 seconds.
exit /b 1

:database_ready

echo Verifying ReliefOS database schema and data...
python scripts\db_init.py
if errorlevel 1 (
	echo.
	echo ERROR: Database initialization failed. The API was not started.
	exit /b 1
)

curl.exe --silent --fail http://localhost:5001/api/districts >nul 2>&1
if not errorlevel 1 (
	echo ReliefOS API is already running on http://localhost:5001.
	echo Startup verification complete.
	exit /b 0
)

echo Starting ReliefOS API on http://localhost:5001...
python -m agent.api
