@echo off
echo Запуск Discord бота...
echo.

REM Проверяем наличие Python
python --version >nul 2>&1
if errorlevel 1 (
    echo Ошибка: Python не найден!
    echo Установите Python 3.8+ и попробуйте снова.
    pause
    exit /b 1
)

REM Проверяем наличие файла .env
if not exist .env (
    echo Ошибка: Файл .env не найден!
    echo Создайте файл .env на основе env.example
    pause
    exit /b 1
)

REM Создаем виртуальное окружение, если его нет
if not exist "venv" (
    echo Создание виртуального окружения...
    python -m venv venv
)

REM Активируем виртуальное окружение и устанавливаем зависимости
call venv\Scripts\activate.bat
pip install -r requirements.txt

REM Запускаем бота
python -m src.bot

pause
