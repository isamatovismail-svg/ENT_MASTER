#!/usr/bin/env bash
set -euo pipefail

APP_DIR=/opt/ent-master
APP_USER=ent

if [[ $EUID -ne 0 ]]; then
  echo "Запустите через sudo: sudo bash $APP_DIR/server/update.sh" >&2
  exit 1
fi

echo "== Резервная копия перед обновлением"
sudo -u "$APP_USER" bash -c "cd $APP_DIR && python3 -m server.backup"

echo "== Код"
if [[ -d "$APP_DIR/.git" ]]; then
  sudo -u "$APP_USER" git -C "$APP_DIR" pull --ff-only
else
  echo "Папка не git-репозиторий: считаю, что новые файлы уже скопированы (rsync)."
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "== Тесты"
sudo -u "$APP_USER" bash -c "cd $APP_DIR && python3 -m unittest -q"

echo "== Банк вопросов"
sudo -u "$APP_USER" python3 "$APP_DIR/seed.py"

echo "== Службы"
cp "$APP_DIR"/server/systemd/ent-master-* /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now ent-master-health.timer
systemctl restart ent-master-site.service
if systemctl is-enabled --quiet ent-master-bot.service; then
  systemctl restart ent-master-bot.service
fi
systemctl --no-pager --lines=5 status ent-master-site.service
