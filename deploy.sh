#!/bin/bash
set -e
echo "🚀 Iniciando deploy ZAKAZ..."
cd /home/agsimoes1/ordo-logistica
source venv/bin/activate
git pull origin main
export $(cat .env | xargs)
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
echo "✅ Deploy concluído!"
echo "⚠️  Reinicie o Gunicorn: sudo systemctl restart zakaz"
