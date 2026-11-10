@echo off
REM FreshCheck: Bifrost aur FreshCheck dono ek saath chalu karta hai (2 alag windows).
REM In dono windows ko band mat karna jab tak demo/kaam chal raha hai.
cd /d "%~dp0"

echo Bifrost start ho raha hai...
start "Bifrost (band mat karna)" cmd /k "npx -y @maximhq/bifrost"

echo Bifrost ke chalne ka intezaar (10 sec)...
timeout /t 25 /nobreak >nul

echo FreshCheck start ho raha hai...
start "FreshCheck (band mat karna)" cmd /k "py -m uvicorn server:app --reload"

timeout /t 5 /nobreak >nul
start "" http://127.0.0.1:8000
echo.
echo Website: http://127.0.0.1:8000    Bifrost dashboard: http://localhost:8080
echo Endpoint badge sirf response dikhata hai; credentials ya model access verify nahi karta.
