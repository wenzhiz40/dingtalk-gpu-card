# 钉钉 GPU 状态卡片

一个运行在 Linux GPU 服务器上的轻量只读监控程序。它定时调用 `nvidia-smi`，把 GPU 利用率、显存、温度、功耗和计算用户汇总到钉钉群中的固定互动卡片，并在 GPU 从高负载降到低负载时按需发送一次可用提醒。

> 本文统一假设服务器配备 NVIDIA GeForce RTX 5090。RTX 5090 只是为了让安装示例保持一致；程序不会写死显卡型号，而是以本机 `nvidia-smi` 的实际检测结果为准。

## 这个项目解决什么问题

多人共用 GPU 服务器时，大家通常需要先 SSH 登录，再运行 `nvidia-smi` 才能判断 GPU 是否可能空闲。本项目把这一步变成钉钉群里的一张固定卡片：

- 不需要给查看者分配 SSH 账号；
- 不需要在查看者电脑上安装客户端；
- 不会每分钟向群里新增一条消息，而是原地更新同一张卡片；
- 服务器只发起出站 HTTPS 请求，不开放 Web 服务或新的入站端口；
- 采集逻辑只读，不提供排队、作业提交、远程控制或任意命令执行能力。

卡片会显示：

- 本机检测到的 GPU 型号和数量；
- 每张 GPU 的利用率、显存、温度和功耗；
- 根据阈值估算的“使用中”或“低占用”；
- NVIDIA 计算任务所属的 Linux 用户名及该用户合计显存；
- 最近更新时间以及采集异常摘要。

卡片不会显示 PID、进程名、命令行、GPU UUID、服务器 IP 或图形桌面任务。

## 工作方式

```text
RTX 5090 服务器
  └─ systemd 每 60 秒运行一次 Python 服务
       ├─ 固定参数调用 /usr/bin/nvidia-smi
       ├─ 在内存中整理 GPU 指标
       ├─ 通过 HTTPS 调用钉钉 OpenAPI
       └─ 原地更新钉钉群中的固定互动卡片
```

程序不监听端口。正常运行时，唯一必要的外部通信是访问 `https://api.dingtalk.com`。

如果一台服务器安装了多张 RTX 5090，程序会在同一张卡片中分别显示每张 GPU。若有多台服务器，建议每台服务器独立运行一份程序并维护自己的卡片，避免多台机器竞争更新同一个卡片实例。

## 已实现的能力

- 自动识别本机 GPU 型号，不依赖手写标题；
- 使用单个富文本变量生成完整卡片内容；
- 首次运行创建并投放卡片，后续只更新原卡片；
- 固定参数执行 `nvidia-smi`，全程使用 `shell=False`；
- 聚合同一用户的多个 NVIDIA 计算任务显存；
- 采集失败时显示安全的错误摘要；
- GPU 从高利用率降到低利用率时发送一次可用提醒；
- 提醒状态和卡片实例状态跨服务重启保存；
- 使用低权限 Linux 用户和加固后的 systemd 服务；
- 不依赖第三方 Python 包，只使用 Python 标准库。

## 环境要求

开始前需要准备：

- 一台 Linux 服务器，示例中假设安装 RTX 5090；
- 可正常工作的 NVIDIA 驱动；
- `/usr/bin/nvidia-smi`；
- Python 3.8 或更高版本；
- systemd；
- 一个可创建企业内部应用和机器人的钉钉组织；
- 服务器能够出站访问 `api.dingtalk.com:443`；
- 一个具有 `sudo` 权限的部署账号。

本项目不要求 Docker、数据库、域名、公网 IP、反向代理或内网穿透。

## 第一步：检查服务器

在 RTX 5090 服务器上执行：

```bash
cat /etc/os-release | grep -E '^(PRETTY_NAME|VERSION_ID)='
python3 --version
command -v nvidia-smi
nvidia-smi --query-gpu=index,name,memory.total,driver_version --format=csv,noheader
timedatectl show -p Timezone --value
systemctl --version | head -n 1
sudo -v
```

确认：

- Python 可以运行；
- `nvidia-smi` 位于 `/usr/bin/nvidia-smi`；
- 输出中能识别 RTX 5090；
- systemd 可用；
- 当前部署账号可以使用 `sudo`。

如果 `nvidia-smi` 本身不能正常工作，应先修复 NVIDIA 驱动或设备权限，再部署本项目。

## 第二步：准备钉钉应用

钉钉开放平台的界面和权限名称可能调整，实际操作请以[钉钉开放平台文档](https://open.dingtalk.com/document/)为准。需要完成以下事项：

1. 在目标组织中创建企业内部应用。
2. 为应用添加企业机器人能力。
3. 创建并发布一个互动卡片模板。
4. 在模板中创建名为 `content` 的公有变量，变量类型必须是“富文本”。
5. 在卡片画布中放置富文本组件，并绑定 `content` 变量。
6. 为应用开通 `Card.Instance.Write` 权限。
7. 如果要启用可用提醒，再开通“企业内机器人发送消息权限”。
8. 发布应用版本，并把机器人加入目标群。
9. 记录 Client ID、Client Secret、卡片模板 ID 和群 `openConversationId`。

四个配置值的用途如下：

- `DINGTALK_CLIENT_ID`：企业内部应用的 Client ID，同时作为机器人标识；
- `DINGTALK_CLIENT_SECRET`：应用密钥，只能保存在服务器本地；
- `DINGTALK_CARD_TEMPLATE_ID`：互动卡片模板 ID，通常以 `.schema` 结尾；
- `DINGTALK_OPEN_CONVERSATION_ID`：接收卡片的群会话 ID。

不要把真实 Client Secret 写进聊天记录、截图、README、代码仓库或命令行参数。

## 第三步：获取代码并运行测试

```bash
git clone https://github.com/wenzhiz40/dingtalk-gpu-card.git
cd dingtalk-gpu-card
python3 -m unittest discover -s tests -v
```

测试应全部显示 `ok`。

可以在不访问钉钉、不创建状态文件的情况下读取一次真实 GPU：

```bash
python3 app.py --dry-run
```

`--dry-run` 会把生成的卡片 JSON 输出到终端。如果这里无法读取 RTX 5090，先检查 `nvidia-smi` 和当前用户的设备访问权限。

## 第四步：创建低权限服务用户

先检查用户是否已经存在：

```bash
getent passwd gpu-card
```

没有输出时创建系统用户：

```bash
sudo useradd \
  --system \
  --user-group \
  --home-dir /nonexistent \
  --shell /usr/sbin/nologin \
  gpu-card
```

验证低权限用户能否读取 GPU：

```bash
sudo -u gpu-card /usr/bin/nvidia-smi \
  --query-gpu=index,name,utilization.gpu,memory.used \
  --format=csv,noheader,nounits
```

只有在出现设备权限错误时，才考虑把用户加入 `video` 组：

```bash
sudo usermod -aG video gpu-card
```

能正常读取时不要增加额外权限。

## 第五步：安装程序

在仓库目录执行：

```bash
sudo install -d -o root -g root -m 0755 /opt/dingtalk-gpu-card

sudo install -o root -g root -m 0644 \
  app.py card_data.py config.py dingtalk_api.py gpu_collector.py \
  /opt/dingtalk-gpu-card/

sudo install -d -o gpu-card -g gpu-card -m 0700 \
  /var/lib/dingtalk-gpu-card

sudo install -o root -g root -m 0644 \
  systemd/dingtalk-gpu-card.service \
  /etc/systemd/system/dingtalk-gpu-card.service

sudo install -o root -g gpu-card -m 0640 \
  .env.example \
  /etc/dingtalk-gpu-card.env
```

安装后的目录用途：

- `/opt/dingtalk-gpu-card`：只读程序文件；
- `/etc/dingtalk-gpu-card.env`：钉钉凭据和运行参数；
- `/var/lib/dingtalk-gpu-card/state.json`：卡片实例、最近一次指标和提醒状态；
- `/etc/systemd/system/dingtalk-gpu-card.service`：systemd 服务定义。

## 第六步：填写配置

使用安全的编辑方式打开配置：

```bash
sudoedit /etc/dingtalk-gpu-card.env
```

示例：

```ini
DINGTALK_CLIENT_ID=<your-client-id>
DINGTALK_CLIENT_SECRET=<your-client-secret>
DINGTALK_CARD_TEMPLATE_ID=<your-card-template-id>.schema
DINGTALK_OPEN_CONVERSATION_ID=<your-open-conversation-id>

CARD_TITLE=
LOCAL_SERVER_NAME=5090服务器

UPDATE_INTERVAL_SECONDS=60
GPU_BUSY_UTIL_PERCENT=10
GPU_BUSY_MEMORY_MIB=1024

GPU_AVAILABLE_ALERTS_ENABLED=true
GPU_AVAILABLE_HIGH_PERCENT=70
GPU_AVAILABLE_LOW_PERCENT=20

STATE_FILE=/var/lib/dingtalk-gpu-card/state.json
```

配置说明：

- `CARD_TITLE`：留空时根据实际检测到的 GPU 型号自动生成标题；填写后使用自定义标题。
- `LOCAL_SERVER_NAME`：这台服务器在卡片内容和提醒中的友好名称。
- `UPDATE_INTERVAL_SECONDS`：刷新间隔，程序不允许小于 30 秒。
- `GPU_BUSY_UTIL_PERCENT`：利用率达到该值时判定为使用中。
- `GPU_BUSY_MEMORY_MIB`：显存占用达到该值时判定为使用中。
- `GPU_AVAILABLE_ALERTS_ENABLED`：是否启用从高负载降到低负载的群提醒。
- `GPU_AVAILABLE_HIGH_PERCENT`：达到该利用率后，为下一次可用提醒布防。
- `GPU_AVAILABLE_LOW_PERCENT`：布防后降到该值以下时发送一次提醒。
- `STATE_FILE`：持久化状态文件路径。

忙闲判断是启发式估算。默认情况下，满足以下任一条件就显示“使用中”：

```text
GPU 利用率 >= 10%
或
显存占用 >= 1024 MiB
```

否则显示“低占用”。这不等同于绝对空闲，使用者仍应结合实际利用率、显存和计算用户判断。

## 第七步：启动服务

```bash
sudo systemctl daemon-reload
sudo systemctl start dingtalk-gpu-card
sudo systemctl status dingtalk-gpu-card --no-pager
sudo journalctl -u dingtalk-gpu-card -n 30 --no-pager
```

首次成功运行后，日志中应出现：

```text
GPU 总览卡片已首次投放，请在群中手动置顶
```

确认目标群收到卡片后启用开机启动：

```bash
sudo systemctl enable dingtalk-gpu-card
```

卡片标题默认取自实际检测到的 GPU 型号，因此在本文假设下会显示为类似：

```text
5090 GPU 状态
```

## GPU 可用提醒

启用提醒后，单张 GPU 的状态过程如下：

1. 利用率达到 `GPU_AVAILABLE_HIGH_PERCENT`，默认为 70%，提醒进入布防状态。
2. 后续采样中利用率首次降到 `GPU_AVAILABLE_LOW_PERCENT` 以下，默认为 20%，机器人发送一次提醒。
3. 发送成功后解除布防，不会在低负载期间重复刷屏。
4. GPU 再次达到高阈值后，才会重新布防。

提醒示例：

```text
GPU 可用提醒
5090服务器 GPU 0（NVIDIA GeForce RTX 5090）可使用：利用率已从 ≥70% 降至 12%。
请结合总览卡片中的显存与计算用户确认。
```

提醒失败不会中断固定卡片更新。如果应用尚未获得群消息权限，可以先设置：

```ini
GPU_AVAILABLE_ALERTS_ENABLED=false
```

## 状态文件与重新投放

`state.json` 用来保存：

- 钉钉卡片的 `outTrackId`；
- 最近一次成功采集的 GPU 指标；
- 最近一次识别到的计算用户名；
- 可用提醒的布防状态。

文件由服务用户写入，权限为 `0600`，所在目录权限为 `0700`。它不包含 Client Secret，但仍属于运行数据，不应提交到 Git，也不应在服务器之间复制。

如果更换了目标群、卡片模板或钉钉应用，并且需要创建一张新卡片：

```bash
sudo systemctl stop dingtalk-gpu-card
sudo rm -- /var/lib/dingtalk-gpu-card/state.json
sudo systemctl start dingtalk-gpu-card
```

删除状态文件会丢失旧卡片实例关联和提醒状态，并在下次运行时创建一张新卡片。旧卡片不会由本程序自动删除。

## 日常运维

```bash
sudo systemctl status dingtalk-gpu-card --no-pager
sudo systemctl restart dingtalk-gpu-card
sudo systemctl stop dingtalk-gpu-card
sudo systemctl start dingtalk-gpu-card
sudo journalctl -u dingtalk-gpu-card -n 50 --no-pager
sudo journalctl -u dingtalk-gpu-card --since today -p warning --no-pager
```

升级代码：

```bash
cd ~/dingtalk-gpu-card
git pull --ff-only
python3 -m unittest discover -s tests -v

sudo install -o root -g root -m 0644 \
  app.py card_data.py config.py dingtalk_api.py gpu_collector.py \
  /opt/dingtalk-gpu-card/

sudo systemctl restart dingtalk-gpu-card
sudo systemctl status dingtalk-gpu-card --no-pager
```

升级时保留原来的 `/etc/dingtalk-gpu-card.env` 和 `state.json`，已有卡片就会继续原地更新。

## 安全与隐私边界

- 服务以无登录权限的 `gpu-card` 用户运行，而不是 root。
- systemd 启用了 `NoNewPrivileges`、只读系统目录、空 capability 集合等限制。
- 钉钉 Secret 只保存在 `/etc/dingtalk-gpu-card.env`，建议权限为 `root:gpu-card 0640`。
- GPU 采集命令和参数完全固定，使用 `shell=False`。
- 群消息、卡片内容和环境变量不能变成服务器命令。
- 服务不监听端口，只发起出站 HTTPS 请求。
- 卡片投放设置 `supportForward=false`。
- 日志不会主动打印 Client Secret 或访问令牌。
- 只显示经 `/proc` 文件所有者解析出的计算用户名和合计显存，不显示 PID、进程名或命令行。
- 如果系统使用 `hidepid` 等策略阻止读取进程归属，程序会显示未检测到可识别计算任务，不要求放宽系统策略。

建议检查：

```bash
sudo systemctl show dingtalk-gpu-card \
  -p User -p Group -p NoNewPrivileges

sudo stat -c '%U %G %a %n' /etc/dingtalk-gpu-card.env
sudo stat -c '%U %G %a %n' /var/lib/dingtalk-gpu-card/state.json
sudo ss -lntp | grep python3
```

最后一条通常没有输出，因为本服务不监听网络端口。

## 多服务器部署

每台服务器都应拥有独立的：

- `/etc/dingtalk-gpu-card.env`；
- `/var/lib/dingtalk-gpu-card/state.json`；
- 钉钉卡片实例。

不同服务器可以使用同一个应用、机器人、卡片模板和群，但不要复制 `state.json`，也不要让多台服务器共享同一个 `outTrackId`。这种“一台服务器一张卡片”的方式能够避免覆盖竞争，并确保任意一台服务器停机时不会影响其他卡片继续更新。

## 故障排查

### `nvidia-smi` 找不到或执行失败

```bash
command -v nvidia-smi
/usr/bin/nvidia-smi
sudo -u gpu-card /usr/bin/nvidia-smi
```

依次确认驱动、固定路径和低权限用户的设备访问权限。

### 返回 `403` 或缺少 `Card.Instance.Write`

在钉钉应用权限管理中开通 `Card.Instance.Write`。权限生效后重启服务，或等待下一轮自动重试。

### 日志显示投放成功，但目标群没有卡片

检查：

- `DINGTALK_OPEN_CONVERSATION_ID` 是否对应目标群；
- 机器人是否已经加入该群；
- 配置中是否误用了旧的 `chatId`；
- `state.json` 是否仍指向此前创建的卡片实例。

确认配置后，如需重新投放，按“状态文件与重新投放”一节删除本机状态文件。

### 卡片模板找不到 `content`

确认 `content` 是公有“富文本”变量，而不是普通文本变量，并确认富文本组件已经绑定该变量。

### 卡片停止更新

```bash
sudo systemctl status dingtalk-gpu-card --no-pager
sudo journalctl -u dingtalk-gpu-card -n 100 --no-pager
```

服务器彻底关机或断网后，程序无法主动把卡片改成离线状态。若卡片中的更新时间长时间不变，应视为服务器或监控服务可能已经停止。

## 项目结构

```text
dingtalk-gpu-card/
├── app.py                         主循环、状态保存、卡片创建与更新
├── card_data.py                   把 GPU 数据转换成卡片富文本
├── config.py                      从环境变量读取并校验配置
├── dingtalk_api.py                最小化钉钉 OpenAPI 客户端
├── gpu_collector.py               固定参数执行并解析 nvidia-smi
├── .env.example                   不含真实凭据的配置模板
├── systemd/
│   └── dingtalk-gpu-card.service  加固后的 systemd 服务
└── tests/                         单元测试
```

## 测试

```bash
python3 -m unittest discover -s tests -v
```

测试覆盖：

- `nvidia-smi` CSV 数据解析；
- 固定命令、`shell=False` 和超时限制；
- 配置校验；
- 卡片忙闲状态与隐私字段；
- 计算用户名显存聚合；
- 卡片投放目标与禁用转发；
- 请求体不包含 Client Secret；
- GPU 可用提醒的布防和单次触发。

## 参考和开源项目说明

开发前期调研和实际阅读过的开源项目是 [psalias2006/gpu-hot](https://github.com/psalias2006/gpu-hot)。GPU Hot 是一个采用 MIT License 的实时 NVIDIA GPU Web 监控面板，支持多项 GPU 指标、历史图表、进程信息和多节点模式。

本项目从 GPU Hot 的展示方式中确认了利用率、显存、温度、功耗和设备自动识别是最有价值的基础指标，但两者的实现和使用场景不同：

- GPU Hot 是浏览器中的实时 Web 面板；本项目输出钉钉固定卡片。
- GPU Hot 自带 Web 服务；本项目不开放入站端口。
- GPU Hot 支持更丰富的实时指标；本项目刻意减少数据和权限范围。
- 本项目没有复制 GPU Hot 的源码、静态资源或容器镜像，也不把 GPU Hot 作为运行依赖。

本仓库的 Python 程序为独立实现，运行时只使用 Python 标准库，并调用系统提供的 [`nvidia-smi`](https://docs.nvidia.com/deploy/nvidia-smi/index.html) 与[钉钉开放平台](https://open.dingtalk.com/document/)接口。当前没有直接引入其他第三方开源库。如果以后复制、修改或打包第三方代码，应同时补充来源、版本和许可证说明。

## 已知限制

- 忙闲状态来自阈值估算，不代表 GPU 一定可被新任务使用。
- 默认每 60 秒采样一次，短于采样间隔的瞬时负载可能不会触发提醒布防。
- 服务器关机后无法主动修改卡片，只能根据最后更新时间判断掉线。
- 当前不保存历史曲线，不提供趋势分析。
- 当前没有排队、作业提交、资源预约或远程控制功能。
- 计算用户名依赖 Linux `/proc` 权限；读取受限时不会显示用户信息。
