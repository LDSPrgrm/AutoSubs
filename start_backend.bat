@echo off
cd /d %~dp0
call conda activate AutoSubs
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
