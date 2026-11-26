#!/usr/bin/env bash
# Первоначальная установка ENT MASTER на сервер Oracle Cloud (Ubuntu 24.04, Always Free).
#
# Запуск на сервере (из папки с кодом проекта или с адресом git-репозитория):
#   sudo bash deploy/setup.sh ent-master.kz                      — код уже лежит в /opt/ent-master
#   sudo bash deploy/setup.sh ent-master.kz https://github.com/…  — склонировать код из git
#
# Что делает скрипт (повторный запуск безопасен):
#   1. ставит python3, git, caddy;
#   2. открывает порты 80 и 443 во встроенном файрволе Ubuntu-образа Oracle (iptables);
#   3. создаёт системного пользователя ent и папки /opt/ent-master, /var/backups/ent-master;
#   4. создаёт .env (если его нет) с SITE_URL, COOKIE_SECURE=1 и папкой копий;
#   5. загружает банк вопросов (seed.py);
#   6. включает службы systemd: сайт, бот (если есть токен), ежедневную копию базы;
#   7. настраивает Caddy: HTTPS-сертификат для домена и прокси на 127.0.0.1:8000.
set -euo pipefail

DOMAIN="${1:-}"
REPO_URL="${2:-}"
APP_DIR=/opt/ent-master
BACKUP_DIR=/var/backups/ent-master
APP_USER=ent

if [[ $EUID -ne 0 ]]; then
  echo "Запустите через sudo: sudo bash deploy/setup.sh <домен> [git-адрес]" >&2
  exit 1
fi
if [[ -z "$DOMAIN" ]]; then
  echo "Укажите домен: sudo bash deploy/setup.sh ent-master.kz [git-адрес]" >&2
  exit 1
fi

echo "== 1. Пакеты"
export DEBIAN_FRONTEND=noninteractive  # без вопросов от iptables-persistent и других пакетов
apt-get update -q
apt-get install -y -q python3 git caddy netfilter-persistent iptables-persistent
python3 - <<'PY'
import sys
if sys.version_info < (3, 11):
    sys.exit(f"Нужен Python 3.11+, установлен {sys.version.split()[0]}. Используйте образ Ubuntu 24.04.")
PY

echo "== 2. Файрвол сервера: порты 80 и 443"
# В образах Ubuntu от Oracle входящие соединения закрыты правилом REJECT в iptables.
# Разрешающие правила вставляем перед ним. Порты нужно открыть ещё и в Security List
# облачной сети (VCN) — это делается в консоли Oracle Cloud, см. README.
for port in 80 443; do
  if ! iptables -C INPUT -p tcp -m state --state NEW --dport "$port" -j ACCEPT 2>/dev/null; then
    position=$(iptables -L INPUT --line-numbers | awk '/REJECT/ {print $1; exit}')
    iptables -I INPUT "${position:-1}" -p tcp -m state --state NEW --dport "$port" -j ACCEPT
  fi
done
netfilter-persistent save

echo "== 3. Пользователь и папки"
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin "$APP_USER"
if [[ ! -f "$APP_DIR/main.py" ]]; then
  if [[ -z "$REPO_URL" ]]; then
    echo "В $APP_DIR нет кода. Скопируйте проект (rsync/scp) или передайте git-адрес вторым аргументом." >&2
    exit 1
  fi
  git clone "$REPO_URL" "$APP_DIR"
fi
mkdir -p "$BACKUP_DIR"
chown -R "$APP_USER:$APP_USER" "$APP_DIR" "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

echo "== 4. Настройки .env"
ENV_FILE="$APP_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  cat > "$ENV_FILE" <<ENV
# Настройки ENT MASTER на сервере. Секреты храните только здесь (файл не попадает в git).
SITE_URL=https://$DOMAIN
COOKIE_SECURE=1
BACKUP_DIR=$BACKUP_DIR
BACKUP_KEEP=14

# Telegram-бот (необязательно):
# TELEGRAM_BOT_TOKEN=

# Почта для кодов подтверждения (Gmail, пароль приложения):
# SMTP_HOST=smtp.gmail.com
# SMTP_PORT=465
# SMTP_USER=
# SMTP_PASSWORD=
# MAIL_FROM=

# Вход через Google (redirect URI: https://$DOMAIN/auth/google/callback):
# GOOGLE_CLIENT_ID=
# GOOGLE_CLIENT_SECRET=
# GOOGLE_REDIRECT_URI=https://$DOMAIN/auth/google/callback
ENV
  echo "Создан $ENV_FILE — впишите в него ключи SMTP, бота и Google."
fi
chown "$APP_USER:$APP_USER" "$ENV_FILE"
chmod 600 "$ENV_FILE"

echo "== 5. Банк вопросов"
sudo -u "$APP_USER" python3 "$APP_DIR/seed.py"

echo "== 6. Службы systemd"
cp "$APP_DIR"/deploy/ent-master-*.service "$APP_DIR"/deploy/ent-master-backup.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now ent-master-site.service ent-master-backup.timer
if grep -Eq '^TELEGRAM_BOT_TOKEN=.+' "$ENV_FILE"; then
  systemctl enable --now ent-master-bot.service
else
  echo "Бот не включён: в .env нет TELEGRAM_BOT_TOKEN (потом: sudo systemctl enable --now ent-master-bot)."
fi

echo "== 7. Caddy и HTTPS"
sed "s/ent-master\.example\.kz/$DOMAIN/g" "$APP_DIR/deploy/Caddyfile" > /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl enable caddy
systemctl reload-or-restart caddy

echo
echo "Готово. Проверьте:"
echo "  https://$DOMAIN                         — сайт (сертификат появится в течение минуты)"
echo "  systemctl status ent-master-site        — состояние сайта"
echo "  journalctl -u ent-master-site -f        — журнал сайта"
echo "  systemctl list-timers ent-master-backup — когда следующая резервная копия"
echo "Назначить администратора: sudo -u $APP_USER python3 $APP_DIR/manage_admin.py <почта>"
