# 钉钉 GPU 状态固定卡片（两台服务器、两张独立卡片）

2080Ti 与 3090 各自在本机每 60 秒运行一次只读采集，并分别更新自己的钉钉卡片。任意一台服务器关机或故障，都不会影响另一台服务器的卡片继续更新。

```text
2080Ti ──本机 nvidia-smi──HTTPS──> 2080Ti 独立卡片
3090   ──本机 nvidia-smi──HTTPS──> 3090 独立卡片
```

每张卡片显示：

- 本机实际检测到的 GPU 型号和数量；
- 每张 GPU 的利用率、显存、温度、功耗和估算忙闲状态；
- NVIDIA 计算任务的用户名及该用户合计占用的显存；
- 本机采集异常与最后成功采集时间；
- 北京时间格式的更新时间。

程序不显示 PID、命令、进程名、GPU UUID 或服务器地址，也不查询图形桌面进程。

## 标题自动识别

`CARD_TITLE` 留空时，程序根据本轮 `nvidia-smi` 的实际型号生成标题，例如：

```text
NVIDIA GeForce RTX 2080 Ti GPU 状态
NVIDIA GeForce RTX 3090 GPU 状态
```

因此即使 3090 的旧配置误写了 `SERVER_NAME=2080Ti`，卡片标题仍会显示实际检测到的 RTX 3090。仍建议把 `LOCAL_SERVER_NAME` 分别改成 `2080Ti服务器` 和 `3090服务器`，因为机器人提醒会使用这个友好名称。

## 配置

两台服务器分别维护自己的 `/etc/dingtalk-gpu-card.env` 和 `state.json`。钉钉凭证、模板 ID、群 ID 可以相同，但 `LOCAL_SERVER_NAME` 应不同。

2080Ti：

```ini
DINGTALK_CLIENT_ID=dingxxxxxxxxxxxxxxxx
DINGTALK_CLIENT_SECRET=请只在服务器本地填写
DINGTALK_CARD_TEMPLATE_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx.schema
DINGTALK_OPEN_CONVERSATION_ID=cidxxxxxxxxxxxxxxxx

CARD_TITLE=
LOCAL_SERVER_NAME=2080Ti服务器
UPDATE_INTERVAL_SECONDS=60
GPU_BUSY_UTIL_PERCENT=10
GPU_BUSY_MEMORY_MIB=1024
GPU_AVAILABLE_ALERTS_ENABLED=true
GPU_AVAILABLE_HIGH_PERCENT=70
GPU_AVAILABLE_LOW_PERCENT=20
STATE_FILE=/var/lib/dingtalk-gpu-card/state.json
```

3090 使用相同结构，只改：

```ini
LOCAL_SERVER_NAME=3090服务器
```

不要在两台服务器之间复制 `state.json`，因为它们保存各自卡片的 `outTrackId` 和提醒状态。

## 钉钉权限

- 固定卡片需要 `Card.Instance.Write`。
- 启用 GPU 可用提醒，还需要“企业内机器人发送消息权限”。
- 机器人必须已经在目标群中。

如果暂时没有消息权限，设置：

```ini
GPU_AVAILABLE_ALERTS_ENABLED=false
```

提醒失败不会阻止固定卡片更新。

## 在两台服务器上升级

分别把新版 `dingtalk-gpu-card` 目录上传到 2080Ti 和 3090，然后在每台服务器执行：

```bash
cd ~/dingtalk-gpu-card
python3 -m unittest discover -s tests -v
sudo install -o root -g root -m 0644 \
  app.py card_data.py config.py dingtalk_api.py gpu_collector.py \
  /opt/dingtalk-gpu-card/
sudoedit /etc/dingtalk-gpu-card.env
sudo systemctl restart dingtalk-gpu-card
sudo systemctl status dingtalk-gpu-card --no-pager
sudo journalctl -u dingtalk-gpu-card -n 30 --no-pager
```

保留两台服务器各自原来的 `state.json`，这样两张已有卡片会原地升级，不会创建新卡片，也不需要重新置顶。

## GPU 可用提醒

某张 GPU 曾达到 `GPU_AVAILABLE_HIGH_PERCENT`（默认 70%）后进入等待状态；以后第一次降到 `GPU_AVAILABLE_LOW_PERCENT`（默认 20%）以下时，本机机器人发送一次：

```text
GPU 可用提醒
3090服务器 GPU 0（NVIDIA GeForce RTX 3090）可使用：利用率已从 ≥70% 降至 12%。
请结合状态卡片中的显存与计算用户确认。
```

提醒发送成功后不会重复；只有该 GPU 再次达到 70% 才会重新布防。状态保存在本机 `state.json`，服务重启不会丢失。

判断基于每 60 秒一次的采样，短于采样间隔的瞬时高负载可能不会触发布防。

## 计算用户显示

程序查询 NVIDIA compute-apps，再使用 `/proc` 的文件所有者把同一用户的多个计算进程合并，例如：

```text
计算用户：userA 4.0 GiB；userB 2.0 GiB
```

不会显示 PID、进程名、命令行或图形桌面任务。如果系统使用 `hidepid` 等策略阻止低权限账号读取归属，卡片会显示“未检测到可识别的计算任务”，程序不会要求放宽系统隐私策略。

## 关机与异常的显示边界

- 服务仍在运行但 `nvidia-smi` 失败时，本机卡片会显示“异常”和安全的故障摘要。
- 服务器彻底关机或断网后，它无法再主动修改自己的卡片。因此卡片会停留在最后一次内容，需要根据“更新时间超过 3 分钟未变化”判断掉线。
- 两张卡片互相独立，所以 2080Ti 掉线不会影响 3090 卡片，反之亦然。

这是不引入第三台常在线服务器时，故障隔离最可靠的方案。

## 演练与测试

```bash
python3 -m unittest discover -s tests -v
python3 app.py --dry-run
```

`--dry-run` 只读取本机 GPU 并输出卡片 JSON，不访问钉钉，也不写状态文件。

## 安全边界

- 每台服务器只执行本机固定参数的 `/usr/bin/nvidia-smi`，全部使用 `shell=False`。
- 服务不监听端口，只向钉钉发出 HTTPS 请求。
- Secret 只保存在权限 `0640` 的服务器配置文件中，日志不会输出 Secret。
- 卡片禁用转发；只显示用户主动要求的计算用户名和合计显存。
- 不显示地址、PID、命令、程序名或 GPU UUID。
- 不提供作业提交、排队或远程控制能力。
