@echo off
set DATABASE_URL=postgresql://reliefos:reliefos@localhost:5433/reliefos
python -m agent.api
