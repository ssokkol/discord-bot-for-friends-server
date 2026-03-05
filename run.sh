djn#!/bin/bash

echo "Запуск Discord бота..."
echo

# Проверяем наличие Python
if ! command -v python3 &> /dev/null; then
    echo "Ошибка: Python 3 не найден!"
    echo "Установите Python 3.8+ и попробуйте снова."
    exit 1
fi

# Проверяем наличие файла .env
if [ ! -f .env ]; then
    echo "Ошибка: Файл .env не найден!"
    echo "Создайте файл .env на основе env.example"
    exit 1
fi

# Создаем виртуальное окружение, если его нет
if [ ! -d "venv" ]; then
    echo "Создание виртуального окружения..."
    python3 -m venv venv
fi

# Активируем виртуальное окружение и устанавливаем зависимости
source venv/bin/activate
pip install -r requirements.txt

# Запускаем бота
python -m src.bot
