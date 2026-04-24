# Déploiement — toitureverte-api sur VPS Ubuntu 22.04

## 1. Prérequis système

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.12 python3.12-venv python3-pip postgresql postgresql-contrib nginx certbot python3-certbot-nginx git

# WeasyPrint system dependencies
sudo apt install -y libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf2.0-0 libffi-dev
```

## 2. PostgreSQL

```bash
sudo -u postgres psql
CREATE DATABASE toitureverte;
CREATE USER toitureverte WITH PASSWORD 'CHANGE_ME';
GRANT ALL PRIVILEGES ON DATABASE toitureverte TO toitureverte;
ALTER DATABASE toitureverte OWNER TO toitureverte;
\q
```

## 3. Projet

```bash
cd /var/www
sudo mkdir toitureverte-api && sudo chown $USER:$USER toitureverte-api
git clone https://github.com/TON_REPO/toitureverte-api.git toitureverte-api
cd toitureverte-api

python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Copier et remplir .env
cp .env.example .env
nano .env   # Remplir toutes les variables

# Migrations + static
export DJANGO_SETTINGS_MODULE=config.settings.prod
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser

# Dossier media
sudo mkdir -p /var/www/toitureverte/media
sudo chown -R www-data:www-data /var/www/toitureverte/media
```

## 4. Gunicorn (systemd service)

```bash
sudo nano /etc/systemd/system/toitureverte-api.service
```

```ini
[Unit]
Description=ToitureVerte Django API
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/toitureverte-api
Environment="DJANGO_SETTINGS_MODULE=config.settings.prod"
ExecStart=/var/www/toitureverte-api/venv/bin/gunicorn \
    --workers 3 \
    --bind unix:/run/toitureverte-api.sock \
    --access-logfile /var/log/toitureverte-api/access.log \
    --error-logfile /var/log/toitureverte-api/error.log \
    config.wsgi:application
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo mkdir -p /var/log/toitureverte-api
sudo chown www-data:www-data /var/log/toitureverte-api
sudo systemctl daemon-reload
sudo systemctl enable toitureverte-api
sudo systemctl start toitureverte-api
```

## 5. Nginx

```bash
sudo nano /etc/nginx/sites-available/toitureverte-api
```

```nginx
server {
    listen 80;
    server_name api.toitureverte.be;

    location /media/ {
        alias /var/www/toitureverte/media/;
        add_header X-Content-Type-Options nosniff;
    }

    location /static/ {
        alias /var/www/toitureverte-api/staticfiles/;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:/run/toitureverte-api.sock;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Host $host;
        proxy_redirect off;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/toitureverte-api /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# SSL (Let's Encrypt)
sudo certbot --nginx -d api.toitureverte.be
```

## 6. Google OAuth — configuration

1. Google Cloud Console → APIs & Services → Credentials
2. Créer un OAuth 2.0 Client ID (Web application)
3. Authorized redirect URIs :
   - `https://www.toitureverte.be/espace-client/callback/google`
4. Copier Client ID et Secret dans `.env`
5. Dans Django admin → Sites → modifier `example.com` → `toitureverte.be`
6. Django admin → Social applications → Ajouter Google avec les clés

## 7. Vérification

```bash
# Status de l'API
sudo systemctl status toitureverte-api

# Logs en temps réel
sudo journalctl -u toitureverte-api -f

# Test API
curl https://api.toitureverte.be/api/v1/dashboard/
```

## 8. Mise à jour (déploiement continu)

```bash
cd /var/www/toitureverte-api
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart toitureverte-api
```
