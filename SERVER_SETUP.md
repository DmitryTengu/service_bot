curl ipinfo.io# Настройка сервера: Шаг 4б

Выполняйте блоки по порядку в окне, где вы вошли на сервер по SSH.
Копируйте только содержимое серого блока (без `root@marine-amber:~#` в начале).
Если после блока появилась ошибка, остановитесь и пришлите её текст.

Токен бота в этом файле не нужен: он вводится скрыто и нигде не показывается.

## Блок А: проверить имя и создать `.env`

Проверка, что имя указывает на сервер (должен вывести IP 91.108.241.164):

```
getent hosts kniga-uslug-minsk.duckdns.org
```

Ввод токена (скрыто: при вставке на экране ничего не появится, это нормально; вставьте правой кнопкой мыши и нажмите Enter):

```
read -rsp "Токен бота: " TOKEN; echo
```

Ввод вашего Telegram ID (число, как в локальном `.env` в строке `ADMIN_IDS`; узнать можно у бота @userinfobot):

```
read -rp "Ваш Telegram ID: " ADMIN; echo
```

Запись файла `.env` (токен берётся из памяти и нигде не печатается):

```
printf 'BOT_TOKEN=%s\nADMIN_IDS=%s\nAUTO_APPROVE=0\nDB_PATH=/opt/kniga/data/bot.db\nWEBAPP_URL=https://kniga-uslug-minsk.duckdns.org:8443\nPORT=8000\n' "$TOKEN" "$ADMIN" > /opt/kniga/.env; unset TOKEN ADMIN; chown kniga:kniga /opt/kniga/.env; chmod 600 /opt/kniga/.env
```

Проверка без показа токена:

```
sed 's/^BOT_TOKEN=.*/BOT_TOKEN=(скрыто)/' /opt/kniga/.env
```

## Блок Б: Caddy (HTTPS на порту 8443)

Порт 443 занят Амнезией, поэтому сайт будет на 8443.

```
cat > /etc/caddy/Caddyfile <<'EOF'
kniga-uslug-minsk.duckdns.org:8443 {
    reverse_proxy 127.0.0.1:8000
}
EOF
caddy validate --config /etc/caddy/Caddyfile && systemctl reload caddy && echo "Caddy: настройка принята"
```

## Блок В: автозапуск бота и сайта

```
cat > /etc/systemd/system/kniga-web.service <<'EOF'
[Unit]
Description=Kniga Uslug Mini App
After=network-online.target
Wants=network-online.target

[Service]
User=kniga
Group=kniga
WorkingDirectory=/opt/kniga
ExecStart=/opt/kniga/venv/bin/python -m webapp.main
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true

[Install]
WantedBy=multi-user.target
EOF
cat > /etc/systemd/system/kniga-bot.service <<'EOF'
[Unit]
Description=Kniga Uslug Telegram bot
After=network-online.target
Wants=network-online.target

[Service]
User=kniga
Group=kniga
WorkingDirectory=/opt/kniga
ExecStart=/opt/kniga/venv/bin/python -m bot.main
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload && systemctl enable --now kniga-web kniga-bot && echo "Службы запущены"
```

## Блок Г: проверка

```
systemctl is-active kniga-web kniga-bot caddy
journalctl -u kniga-bot -n 4 --no-pager
curl -s http://127.0.0.1:8000/api/categories | head -c 120; echo
curl -sI https://kniga-uslug-minsk.duckdns.org:8443/ | head -3
```

Ожидаю:
- три раза `active`;
- в журнале бота строка про `Run polling for bot @kniga_uslug_bot`;
- список категорий;
- ответ `HTTP/2 200` по HTTPS.

Сертификат Caddy получает при первом обращении, это может занять до минуты. Если последняя команда не ответила сразу, подождите минуту и повторите.

## После зелёной проверки

Откройте на телефоне **без VPN** адрес `https://kniga-uslug-minsk.duckdns.org:8443` в браузере, затем бота в Telegram: `/menu` и кнопка «Открыть каталог».
