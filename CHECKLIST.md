# Checklist de configuration — ToitureVerte

Tout ce qu'il faut configurer avant la mise en production.
Cocher chaque point une fois terminé.

---

## 1. Variables d'environnement

### API Django (VPS IONOS)

Créer `/opt/toitureverte-api/.env` :

```env
# Django
SECRET_KEY=<générer avec: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())">
DEBUG=False
ALLOWED_HOSTS=api.toitureverte.be,localhost

# Base de données
DATABASE_URL=postgres://toitureverte:<mot_de_passe>@localhost:5432/toitureverte_db

# Email (SMTP Brevo ou Mailgun)
EMAIL_HOST=smtp-relay.brevo.com
EMAIL_PORT=587
EMAIL_HOST_USER=<votre_email_brevo>
EMAIL_HOST_PASSWORD=<clé_api_brevo>
DEFAULT_FROM_EMAIL=noreply@toitureverte.be

# OAuth Google
GOOGLE_CLIENT_ID=<voir section 2>
GOOGLE_CLIENT_SECRET=<voir section 2>

# OAuth Apple
APPLE_CLIENT_ID=<voir section 3>
APPLE_TEAM_ID=<voir section 3>
APPLE_KEY_ID=<voir section 3>
APPLE_PRIVATE_KEY=<contenu du fichier .p8>

# CORS
CORS_ALLOWED_ORIGINS=https://www.toitureverte.be,https://toitureverte.be

# Sécurité
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

### Nuxt (même VPS ou Netlify/Vercel)

Créer `.env` dans le dossier Nuxt :

```env
NUXT_PUBLIC_API_BASE=https://api.toitureverte.be
NUXT_PUBLIC_SITE_URL=https://www.toitureverte.be
```

---

## 2. Google OAuth (pour "Se connecter avec Google")

- [ ] Aller sur https://console.cloud.google.com/
- [ ] Créer un projet "ToitureVerte" (ou utiliser existant)
- [ ] Menu → API et services → Identifiants → Créer des identifiants → ID client OAuth
- [ ] Type d'application : **Application Web**
- [ ] Origines JavaScript autorisées :
  - `https://www.toitureverte.be`
  - `https://api.toitureverte.be`
- [ ] URI de redirection autorisés :
  - `https://api.toitureverte.be/api/v1/auth/google/callback/`
- [ ] Copier **Client ID** et **Client Secret** → mettre dans `.env`
- [ ] Menu → Écran de consentement OAuth → remplir : nom app, email support, logo, politique de confidentialité (`https://www.toitureverte.be/privacy`)
- [ ] Ajouter scopes : `email`, `profile`
- [ ] Passer en **Production** (sinon limité à 100 utilisateurs test)

---

## 3. Apple Sign In (pour "Se connecter avec Apple")

- [ ] Aller sur https://developer.apple.com/account/
- [ ] Nécessite un compte Apple Developer (99 USD/an)
- [ ] Certificates, Identifiers & Profiles → Identifiers → + → App ID → App
  - Bundle ID : `be.toitureverte.app`
  - Activer **Sign In with Apple**
- [ ] Identifiers → + → Services ID
  - Identifier : `be.toitureverte.web`
  - Configurer Sign In with Apple :
    - Domaines : `www.toitureverte.be`
    - Return URLs : `https://api.toitureverte.be/api/v1/auth/apple/callback/`
- [ ] Keys → + → créer une clé avec **Sign In with Apple** activé
  - Télécharger le fichier `.p8` (une seule fois !)
  - Copier Key ID
- [ ] Copier Team ID (en haut à droite sur developer.apple.com)
- [ ] Remplir les variables `APPLE_*` dans `.env`

---

## 4. Base de données PostgreSQL

Sur le VPS IONOS :

```bash
sudo apt install postgresql postgresql-contrib
sudo -u postgres psql
CREATE USER toitureverte WITH PASSWORD 'mot_de_passe_fort';
CREATE DATABASE toitureverte_db OWNER toitureverte;
GRANT ALL PRIVILEGES ON DATABASE toitureverte_db TO toitureverte;
\q
```

- [ ] Base créée
- [ ] Utilisateur créé avec mot de passe fort
- [ ] URL dans `.env`

---

## 5. Déploiement Django sur VPS IONOS

```bash
# Dépendances système
sudo apt update
sudo apt install python3-pip python3-venv nginx certbot python3-certbot-nginx
sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b  # WeasyPrint

# App
cd /opt
git clone https://github.com/TON_REPO/toitureverte-api.git
cd toitureverte-api
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Django
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

### Gunicorn (systemd service)

Créer `/etc/systemd/system/toitureverte-api.service` :

```ini
[Unit]
Description=ToitureVerte Django API
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/toitureverte-api
ExecStart=/opt/toitureverte-api/venv/bin/gunicorn config.wsgi:application \
    --workers 3 --bind 127.0.0.1:8000 --timeout 120
Restart=always
EnvironmentFile=/opt/toitureverte-api/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable toitureverte-api
sudo systemctl start toitureverte-api
```

- [ ] Gunicorn démarre sans erreur : `systemctl status toitureverte-api`
- [ ] Migrations appliquées
- [ ] Superuser créé

---

## 6. Nginx + SSL (HTTPS)

### Config Nginx : `/etc/nginx/sites-available/toitureverte-api`

```nginx
server {
    listen 80;
    server_name api.toitureverte.be;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /opt/toitureverte-api/staticfiles/;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/toitureverte-api /etc/nginx/sites-enabled/
sudo certbot --nginx -d api.toitureverte.be
sudo systemctl reload nginx
```

- [ ] DNS `api.toitureverte.be` → IP du VPS configuré
- [ ] Certificat SSL Let's Encrypt obtenu
- [ ] HTTPS fonctionne : `curl https://api.toitureverte.be/api/v1/`

---

## 7. DNS (chez votre registrar)

| Nom | Type | Valeur |
|-----|------|--------|
| `@` (toitureverte.be) | A | IP du VPS |
| `www` | CNAME | `toitureverte.be` |
| `api` | A | IP du VPS |
| `@` | MX | Serveur email (Brevo/Mailgun) |
| `@` | TXT | SPF : `"v=spf1 include:spf.brevo.com ~all"` |
| `brevo._domainkey` | TXT | DKIM fourni par Brevo |

- [ ] DNS propagé (vérifier avec `dig www.toitureverte.be`)
- [ ] SPF configuré (évite les spams)
- [ ] DKIM configuré

---

## 8. Email transactionnel (Brevo — anciennement Sendinblue)

- [ ] Créer un compte sur https://www.brevo.com
- [ ] Ajouter et vérifier le domaine `toitureverte.be`
- [ ] Configurer DKIM + SPF (Brevo vous donne les records DNS)
- [ ] Récupérer les identifiants SMTP → mettre dans `.env`
- [ ] Tester : `python manage.py shell -c "from django.core.mail import send_mail; send_mail('Test', 'OK', 'noreply@toitureverte.be', ['votre@email.com'])"`

---

## 9. Google Search Console

- [ ] Aller sur https://search.google.com/search-console
- [ ] Ajouter propriété `https://www.toitureverte.be`
- [ ] Vérifier via balise HTML meta (la plus simple avec Nuxt — ajouter dans `useSeoMeta`)
- [ ] Soumettre le sitemap : `https://www.toitureverte.be/sitemap.xml`
- [ ] Vérifier qu'il n'y a pas d'erreurs d'indexation

---

## 10. Google Business Profile (ancien Google My Business)

**PRIORITÉ HAUTE — impact direct sur le SEO local Bruxelles**

- [ ] Aller sur https://business.google.com
- [ ] Créer/revendiquer la fiche "ToitureVerte"
- [ ] Remplir :
  - Nom : `ToitureVerte` (exactement comme sur le site)
  - Catégorie : **Entrepreneur en toiture** + **Paysagiste**
  - Adresse : adresse physique à Bruxelles (obligatoire pour le SEO local)
  - Zone de service : sélectionner les 19 communes + environs
  - Horaires : lundi–vendredi 8h–18h
  - Téléphone : numéro belge
  - Site web : `https://www.toitureverte.be`
  - Description : mentionner "toiture verte Bruxelles", "RENOLUTION", prix TVA 6%
- [ ] Ajouter des photos (avant/après, équipe, chantiers)
- [ ] Vérification par courrier postal (5–7 jours)
- [ ] Une fois vérifié : activer les **Posts** réguliers (actualités, offres)

---

## 11. Google Analytics 4

- [ ] Créer une propriété GA4 sur https://analytics.google.com
- [ ] Récupérer le Measurement ID (`G-XXXXXXXXXX`)
- [ ] Ajouter dans `nuxt.config.ts` :

```ts
// Dans nuxt.config.ts
app: {
  head: {
    script: [
      {
        src: 'https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX',
        async: true,
      },
      {
        innerHTML: `window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
gtag('js', new Date());
gtag('config', 'G-XXXXXXXXXX', { anonymize_ip: true });`,
      },
    ],
  },
},
```

- [ ] Vérifier que les visites apparaissent dans GA4 en temps réel
- [ ] Configurer les événements de conversion (soumission formulaire contact)

---

## 12. Bing Webmaster Tools

- [ ] Aller sur https://www.bing.com/webmasters
- [ ] Ajouter et vérifier le site
- [ ] Soumettre le sitemap
- [ ] (Bonus : Bing alimente aussi Yahoo et DuckDuckGo)

---

## 13. Politique de confidentialité (RGPD)

- [ ] Créer une page `/privacy` sur le site Nuxt
- [ ] Mentionner : Google Analytics (avec anonymize_ip), Google/Apple OAuth, cookies de session
- [ ] Ajouter un bandeau cookies basique (ou utiliser `nuxt-cookie-control`)
- [ ] Lien vers `/privacy` dans le footer et dans la fiche Google Business

---

## 14. Sauvegardes

Sur le VPS :

```bash
# Backup automatique PostgreSQL — cron quotidien
echo "0 3 * * * pg_dump toitureverte_db | gzip > /backup/db_$(date +%Y%m%d).sql.gz" | crontab -
```

- [ ] Backup DB configuré (quotidien)
- [ ] Backup des fichiers media (si upload de photos de chantiers)
- [ ] Tester la restauration une fois

---

## 15. Tests avant mise en ligne

- [ ] `pytest` — tous les tests Django passent
- [ ] `npx playwright test` — tous les tests E2E passent
- [ ] Google PageSpeed Insights sur `https://www.toitureverte.be` : score > 80 mobile
- [ ] Test hreflang : https://technicalseo.com/tools/hreflang/
- [ ] Test JSON-LD : https://search.google.com/test/rich-results
- [ ] Test mobile-friendly : https://search.google.com/test/mobile-friendly
- [ ] Vérifier HTTPS avec SSL Labs : https://www.ssllabs.com/ssltest/

---

## 16. Optimisation og:image

- [ ] Modifier `public/og-image.svg` avec vos vraies photos de chantier
- [ ] Idéalement : générer une version `.png` 1200×630 (les SVG ne sont pas toujours supportés par tous les réseaux sociaux)
- [ ] Tester avec https://www.opengraph.xyz/

---

## Ordre recommandé

1. Variables d'environnement + DB PostgreSQL + déploiement Django
2. DNS + SSL
3. Google Search Console + sitemap
4. Google Business Profile ← **impact SEO le plus rapide**
5. Google Analytics
6. Google OAuth + Apple Sign In (pour l'espace client)
7. Email transactionnel
8. RGPD / politique de confidentialité
9. Tests complets
10. og:image finale
