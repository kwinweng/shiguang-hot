# 内网版登录：180 天免登录

浏览器自带的账号密码弹窗（Basic Auth）只把密码记在内存里，关掉浏览器就忘了，服务器没法给它设有效期。所以内网版改用 `tools/login_gate.py`：

- 有一个登录页，登录成功后发一个签名 Cookie（`HttpOnly`、`SameSite=Lax`，走 HTTPS 时加 `Secure`）。
- Cookie 默认 180 天有效。用 nginx 时，每次访问都会把有效期往后续，只要 180 天内来过就不用再登录；Caddy 下不续期，从登录那天起算 180 天。
- 改密码后，所有设备上的旧 Cookie 都会失效。
- 同一个 IP 15 分钟内输错 10 次，会被暂时挡住。

服务只监听 `127.0.0.1:8780`，由 nginx（`auth_request`）或 Caddy（`forward_auth`）向它确认访问者是否已登录。它只用到 Python 标准库。

## 1. 设密码、起服务

```sh
python3 tools/login_gate.py passwd <账号>      # 交互式输入，至少 8 位
python3 tools/login_gate.py serve               # 默认 180 天；--days 365 可改（浏览器最多认 400 天）
```

账号（PBKDF2 哈希）和签名密钥都存在 `~/.config/shiguang-login/`，权限 600，不进 git。可以用 `LOGIN_GATE_DIR` 换个位置。

服务要常驻，可以交给 systemd、launchd，或者容器里已有的进程管理器。下面是 systemd 的例子：

```ini
# /etc/systemd/system/shiguang-login.service
[Service]
ExecStart=/usr/bin/python3 /workspace/tg-site/tools/login_gate.py serve
User=<跑网站的用户>
Restart=always
[Install]
WantedBy=multi-user.target
```

## 2a. nginx

在 server 块里加两个 location：

```nginx
location = /__login/check {
    internal;
    proxy_pass http://127.0.0.1:8780;
    proxy_pass_request_body off;
    proxy_set_header Content-Length "";
    proxy_set_header X-Forwarded-Proto $scheme;
}
location /__login/ {
    proxy_pass http://127.0.0.1:8780;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
}
location @login { return 302 /__login/?next=$request_uri; }
```

然后在原来有 `auth_basic` / `auth_basic_user_file` 的每个 location 里，把这两行换成：

```nginx
    auth_request /__login/check;
    auth_request_set $login_cookie $upstream_http_set_cookie;
    add_header Set-Cookie $login_cookie;
    error_page 401 = @login;
```

如果 auth_basic 写在 server 层，就把这四行也放在 server 层，同时在上面三个 `/__login` 相关的 location 里各加一行 `auth_request off;`。

注意：一个 location 里只要写了 `add_header`，就不再继承 server 层的 `add_header`。如果原来在 server 层加过别的头（比如 HSTS），要在这个 location 里补写一遍。

## 2b. Caddy

```caddy
handle /__login/* {
    reverse_proxy 127.0.0.1:8780
}
@private path /mail/* /archive/* / /index.html /all.html
handle @private {
    forward_auth 127.0.0.1:8780 {
        uri /__login/check
    }
    file_server
}
```

把原来的 `basic_auth` 块删掉。未登录的访问会被服务直接 302 到登录页（它通过 Caddy 传来的 `X-Forwarded-Uri` 识别这种情况）。

## 3. 检查

1. 不带 Cookie 打开 `/mail/`，应该跳到 `/__login/?next=/mail/`。
2. 登录后回到 `/mail/`。
3. 关掉浏览器再打开 `/mail/`，应该不用再登录。
4. 访问 `/__login/logout` 可以退出登录。

`python3 -m unittest tests.test_login_gate` 覆盖了签发、篡改、过期、改密码、续期、跳转白名单和限速。
