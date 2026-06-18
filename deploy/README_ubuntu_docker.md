# Ubuntu 内网 Docker 部署说明

## 1. 准备目录

```bash
sudo mkdir -p /opt/oil-research
sudo chown -R "$USER:$USER" /opt/oil-research
```

将项目放到 `/opt/oil-research`，并在服务器上准备：

- `.env`：从 `deploy/env.example` 复制。
- `app/config/app_config.json`：生产配置，真实密钥只放服务器。
- `deploy/certs/oil-research.crt` 和 `deploy/certs/oil-research.key`：内网 HTTPS 证书。

生产配置里建议：

- `auth.cookie_secure=true`
- 初始管理员密码改为强密码
- 数据库 URL 指向内网 PostgreSQL
- 所有 API key 完成轮换后再上线

## 2. 启动

```bash
docker compose -p oilresearch up -d --build
docker compose -p oilresearch ps
curl -k https://127.0.0.1/health
```

## 3. 服务托管与自动重启

```bash
sudo cp deploy/systemd/oil-research.service /etc/systemd/system/oil-research.service
sudo systemctl daemon-reload
sudo systemctl enable --now oil-research
sudo systemctl status oil-research
```

Compose 内部已设置 `restart: unless-stopped`，容器异常退出会自动拉起。

## 4. 反向代理与 HTTPS

Nginx 容器监听 `80/443`，`80` 自动跳转到 `443`，后端只在 Docker 网络内暴露 `8036`。

证书可以使用内网 CA 或自签证书。自签示例：

```bash
mkdir -p deploy/certs
openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
  -keyout deploy/certs/oil-research.key \
  -out deploy/certs/oil-research.crt \
  -subj "/CN=oil-research.local"
```

## 5. 日志轮转

Docker 日志使用 `json-file`，单文件 50MB，保留 10 个文件。Nginx 访问日志挂载到 `logs/nginx`，如需系统级轮转，可增加：

```text
/opt/oil-research/logs/nginx/*.log {
  daily
  rotate 14
  compress
  missingok
  notifempty
  copytruncate
}
```

## 6. 健康检查

- 应用容器：`http://127.0.0.1:8036/health`
- Nginx 容器：`http://127.0.0.1/health`
- 外部访问：`https://服务器内网IP/health`

## 7. 发布前检查

```bash
docker compose -p oilresearch config
docker compose -p oilresearch up -d --build
docker compose -p oilresearch ps
docker compose -p oilresearch logs --tail=200 oil-research-app
curl -k https://127.0.0.1/health
```
