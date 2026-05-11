# RingTurn CI/CD 持续集成与持续部署

## 1. 概述

本文档描述 RingTurn 项目的 CI/CD 流程配置，包括 GitLab Runner 部署、流水线设计以及各阶段的执行逻辑。正常应该用云服务器跑runner的，但由于gitlab是私服，服务器访问内网很麻烦（如linux的njuvpn文档是19年的而且很复杂，windows server版本的easyconnect有已知bug会自动掉线），所以就只用本地机器跑了基础的检查。

### 1.1 基础设施

| 项目 | 配置 |
|------|------|
| GitLab 地址 | http://172.29.4.49 |
| Runner 部署位置 | 本地 Windows 机器 (WSL2) |
| Runner 执行器 | shell (bash) |
| Runner 标签 | `shell` |

### 1.2 流水线阶段

```
┌─────────────┐
│    lint    │ ← 代码检查 (ruff / eslint)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   build    │ ← 前端构建 (Vite)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│    test    │ ← 后端测试 (pytest)
└─────────────┘
```

### 1.3 触发规则

| 分支 | lint | build | test |
|------|------|-------|------|
| MR (任意分支) | ✓ | ✓ | ✓ |
| 非 main 分支 | ✓ | ✓ | ✓ |
| main 分支 (合并时) | ✓ | ✓ | ✗ |

---

## 2. GitLab Runner 部署

### 2.1 部署环境

- **操作系统**: Windows 10/11 + WSL2 (Ubuntu)
- **网络**: 可访问 GitLab 服务器 (http://172.29.4.49)
- **Runner 版本**: GitLab Runner 18.11.2

### 2.2 WSL2 环境准备

1. 确保 WSL2 已安装并启用：

```powershell
# 以管理员身份运行 PowerShell
wsl --install
```

2. 进入 WSL 环境：

```bash
wsl -d Ubuntu
```

3. 更新系统并安装必要工具：

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y curl sudo
```

### 2.3 安装 GitLab Runner

```bash
# 下载 GitLab Runner
curl -L https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.deb.sh | sudo bash

# 安装 GitLab Runner
sudo apt-get install gitlab-runner

# 验证安装
gitlab-runner --version
```

### 2.4 注册 Runner

```bash
# 进入 WSL 并注册 Runner
sudo gitlab-runner register \
  --non-interactive \
  --url "http://172.29.4.49" \
  --token "<your-runner-token>" \
  --executor "shell" \
  --description "my-wsl-runner1" \
  --tag-list "shell" \
  --run-untagged="true"
```

> **获取 Runner Token**: GitLab → 项目 → Settings → CI/CD → Runners → Specific runners → Token

### 2.5 启动 Runner 服务

```bash
# 启动 Runner
sudo gitlab-runner start

# 查看 Runner 状态
sudo gitlab-runner status

# 查看 Runner 日志
sudo gitlab-runner run --debug
```

### 2.6 验证 Runner

在 GitLab → Settings → CI/CD → Runners 页面，应能看到注册的 Runner，状态为 **green (active)**。

---

## 3. 流水线配置 (.gitlab-ci.yml)

### 3.1 完整配置

```yaml
stages:
  - lint
  - build
  - test

# ============================================
# 阶段 1: 代码检查
# ============================================
lint-backend:
  stage: lint
  script:
    - cd backend
    - pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -q ruff
    - ruff check app/ --select=F821,F822,F823 --ignore=I
  tags:
    - shell
  rules:
    - if: $CI_MERGE_REQUEST_IID
    - if: $CI_COMMIT_BRANCH != "main"

lint-frontend:
  stage: lint
  script:
    - cd frontend
    - npm ci
    - npm run lint
  tags:
    - shell
  rules:
    - if: $CI_MERGE_REQUEST_IID
    - if: $CI_COMMIT_BRANCH != "main"

# ============================================
# 阶段 2: 构建
# ============================================
build-frontend:
  stage: build
  script:
    - cd frontend
    - npm ci
    - npx vite build
  tags:
    - shell
  rules:
    - if: $CI_MERGE_REQUEST_IID
    - if: $CI_COMMIT_BRANCH != "main"

# ============================================
# 阶段 3: 测试
# ============================================
test-backend:
  stage: test
  script:
    - cd backend
    - apt-get update -qq && apt-get install -y -qq fluidsynth > /dev/null 2>&1
    - pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
    - python3 -m pytest tests/ -v --tb=short
  tags:
    - shell
  rules:
    - if: $CI_MERGE_REQUEST_IID
    - if: $CI_COMMIT_BRANCH != "main"
```

### 3.2 阶段说明

| 阶段 | Job | 执行内容 | 触发条件 |
|------|-----|----------|----------|
| `lint` | `lint-backend` | 后端代码检查 (ruff) | MR 或非 main 分支 |
| `lint` | `lint-frontend` | 前端代码检查 (eslint) | MR 或非 main 分支 |
| `build` | `build-frontend` | 前端构建 (Vite) | MR 或非 main 分支 |
| `test` | `test-backend` | 后端单元测试 (pytest) | MR 或非 main 分支 |

### 3.3 触发规则解释

```yaml
rules:
  - if: $CI_MERGE_REQUEST_IID    # 触发于：创建 Merge Request
  - if: $CI_COMMIT_BRANCH != "main"  # 触发于：非 main 分支的提交
```

### 3.3 rules 规则解释

```yaml
rules:
  - if: $CI_MERGE_REQUEST_IID    # 触发于：创建 Merge Request
  - if: $CI_COMMIT_BRANCH != "main"  # 触发于：非 main 分支的提交
```

这意味着：
- 推送到任何非 main 分支时，触发流水线
- 创建 MR 时，触发流水线
- 推送到 main 分支且无 MR 时，**不触发**（可按需修改）

---

## 4. 各阶段详解

### 4.1 Lint 阶段

#### 后端代码检查

```bash
cd backend
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -q ruff
ruff check app/ --select=F821,F822,F823 --ignore=I
```

| 参数 | 说明 |
|------|------|
| `--select=F821` | 未定义名称检测 |
| `--select=F822` | 未定义名称 (name 定义) |
| `--select=F823` | 局部变量引用前未绑定 |
| `--ignore=I` | 忽略导入顺序检查 |

#### 前端代码检查

```bash
cd frontend
npm ci
npm run lint
```

### 4.2 Build 阶段

#### 前端构建

```bash
cd frontend
npm ci
npx vite build
```

产物：生成 `frontend/dist/` 目录，包含静态资源文件。

### 4.3 Test 阶段

#### 后端测试

```bash
cd backend
apt-get update -qq && apt-get install -y -qq fluidsynth > /dev/null 2>&1
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
python3 -m pytest tests/ -v --tb=short
```

| 步骤 | 说明 |
|------|------|
| `apt-get install fluidsynth` | 安装音频渲染工具 (测试用) |
| `pip install requirements.txt` | 安装 Python 依赖 |
| `pytest tests/` | 执行测试用例 |

---

## 5. 执行器说明 (shell)

### 5.1 Shell 执行器特点

| 特性 | 说明 |
|------|------|
| 环境 | 在 WSL2 的 bash 环境中执行 |
| 工作目录 | Git 仓库根目录 |
| 隔离性 | 无容器隔离，多 job 共享环境 |
| 缓存 | 可使用项目级缓存 |

### 5.2 WSL2 路径映射

由于 Runner 运行在 WSL2 中，Windows 路径需要转换：

| Windows | WSL2 |
|---------|------|
| `C:\projects\ringturn` | `/mnt/c/projects/ringturn` |
| `D:\data` | `/mnt/d/data` |

> **注意**: `.env` 文件中的路径需要使用 WSL2 格式。

### 5.3 环境要求

WSL2 环境中需要安装：

```bash
# Python 环境
sudo apt install -y python3 python3-pip python3-venv

# Node.js 环境 (前端构建)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Git
sudo apt install -y git

# 其他工具
sudo apt install -y ffmpeg fluidsynth
```

---

## 6. 常见问题

### 6.1 Runner 显示离线

**问题**: GitLab 页面上 Runner 显示为灰色 "offline"

**解决**:
1. 检查 WSL2 中 Runner 服务是否运行：
   ```bash
   sudo gitlab-runner status
   ```

2. 重启 Runner：
   ```bash
   sudo gitlab-runner restart
   ```

3. 查看 Runner 日志：
   ```bash
   sudo gitlab-runner run --debug 2>&1 | tail -100
   ```

### 6.2 Job 一直处于 pending

**问题**: Job 提交后一直处于 "pending" 状态

**解决**:
1. 确认 Runner 标签与 job 的 tags 匹配
2. 检查 Runner 是否被禁用
3. 查看 Runner 日志确认心跳正常

### 6.3 权限问题

**问题**: `permission denied` 错误

**解决**:
```bash
# 赋予 GitLab Runner 足够权限
sudo usermod -aG sudo gitlab-runner
sudo chmod -R 755 /home/gitlab-runner
```

### 6.4 路径问题

**问题**: 找不到文件或模块

**解决**:
- 确认工作目录是否正确（`.gitlab-ci.yml` 中的 `cd` 命令）
- Windows 和 WSL2 路径混用会导致问题
- 使用绝对路径而非相对路径

---

## 7. 扩展流水线

### 7.1 添加部署阶段

如需添加生产部署，可在 `.gitlab-ci.yml` 中增加：

```yaml
stages:
  - lint
  - build
  - test
  - deploy

deploy-backend:
  stage: deploy
  script:
    - cd backend
    - echo "部署脚本..."
  tags:
    - shell
  only:
    - main
```

### 7.2 添加定时任务

```yaml
daily-cleanup:
  stage: .pre
  script:
    - rm -rf backend/.pytest_cache
  when: manual
  only:
    - main
  rules:
    - if: $CI_PIPELINE_SOURCE == "schedule"
```

### 7.3 添加缓存

```yaml
build-frontend:
  stage: build
  cache:
    key: frontend-$CI_COMMIT_REF_SLUG
    paths:
      - frontend/node_modules/
  script:
    - cd frontend
    - npm ci
    - npx vite build
```

---

## 8. 安全建议

1. **敏感变量**: API Key 等敏感信息应存储在 GitLab CI/CD Variables 中，而非代码仓库
2. **最小权限**: Runner 使用专用用户运行，避免 root
3. **网络隔离**: 生产部署建议使用 VPN 或专线
4. **定期更新**: 及时更新 GitLab Runner 版本以修复安全漏洞

---

## 9. 参考资料

- [GitLab Runner 文档](https://docs.gitlab.com/runner/)
- [GitLab CI/CD 配置](https://docs.gitlab.com/ee/ci/)
- [Shell executor](https://docs.gitlab.com/runner/executors/shell.html)
- [WSL2 文档](https://docs.microsoft.com/en-us/windows/wsl/)
