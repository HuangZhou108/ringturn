# FluidSynth 部署说明

## 什么是 FluidSynth？

FluidSynth 是一个**将 MIDI 文件转换为音频的工具**。它需要两部分：

1. **FluidSynth 程序** - 负责MIDI→音频的转换
2. **音色库文件(.sf2)** - 提供各种乐器的声音样本

## 部署方式

### 方式一：直接安装（推荐用于开发测试）⭐

```bash
# macOS
brew install fluid-Synth

# Ubuntu/Debian
sudo apt-get install fluidsynth fluid-soundfont-gm

# Windows
# 下载安装包：https://www.fluidsynth.org/
# 或使用包管理器：winget install Fluidsynth
```

安装后，你需要在 `backend/soundfonts/` 目录放一个 `.sf2` 音色库文件。

### 方式二：Docker 部署（推荐用于生产环境）⭐

```bash
# 创建 Dockerfile
cat > backend/Dockerfile << 'EOF'
FROM python:3.10-slim

# 安装 FluidSynth 和基础音频库
RUN apt-get update && apt-get install -y \
    fluidsynth \
    libfluidsynth3 \
    && rm -rf /var/lib/apt/lists/*

# 复制应用代码
COPY . /app
WORKDIR /app

# 安装 Python 依赖
RUN pip install -r requirements.txt

# 放入音色库（需要手动下载）
# COPY GeneralUserGS.sf2 /app/soundfonts/

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0"]
EOF

# 构建镜像
docker build -t ringturn-backend .

# 运行（需要挂载音色库目录）
docker run -p 8000:8000 \
  -v $(pwd)/soundfonts:/app/soundfonts \
  ringturn-backend
```

### 方式三：Python 库（pyfluidsynth）⭐⭐

```bash
pip install pyfluidsynth
```

但这个库在Windows上安装复杂，不推荐。

## 快速开始（最简单的方式）

### Step 1: 安装 FluidSynth

**Windows:**
1. 访问 https://www.fluidsynth.org/
2. 下载 Windows 安装包
3. 安装到默认位置

**macOS:**
```bash
brew install fluid-Synth
```

**Ubuntu:**
```bash
sudo apt-get install fluidsynth
```

### Step 2: 下载音色库

推荐下载 **GeneralUser GS**（70MB，通用好听）：

1. 访问：https://schristiancollins.com/generaluser.php
2. 点击 "Download GeneralUser GS Soundfont v1.44"
3. 解压得到 `GeneralUser GS.sf2`

### Step 3: 配置路径

```bash
# 创建目录并放入音色库
cd backend
mkdir -p soundfonts
# 把下载的 GeneralUser GS.sf2 放入 soundfonts/

# 编辑 .env 文件
SOUNDFONT_PATH=./soundfonts/GeneralUser GS.sf2
```

### Step 4: 验证安装

```bash
# 测试 FluidSynth 是否可用
fluidsynth --version

# 如果输出版本号，说明安装成功
# FluidSynth version 2.3.1
```

## Windows 用户特别说明

### 方法A: WSL（推荐）⭐

如果你用 Windows + WSL（Windows Subsystem for Linux），在 WSL 里安装更简单：

```bash
# 在 WSL 终端中
sudo apt-get install fluidsynth fluid-soundfont-gm

# 后续配置和 Linux 完全一样
```

### 方法B: 直接 Windows 安装

1. 下载：https://github.com/FluidSynth/fluidSynth/releases
2. 解压到 `C:\Program Files\FluidSynth\`当然也可以不放这
3. 添加到系统 PATH 环境变量
4. 在 `.env` 中设置：
   ```
   FLUIDSYNTH_PATH=C:\Program Files\FluidSynth\bin\fluidsynth.exe
   ```

## 代码调用方式

当前 `tools.py` 中的 `render_audio` 是 Mock，需要改成：

```python
async def render_audio(self, midi_path, instruments, output_path, duration):
    """使用 FluidSynth 渲染音频"""
    import subprocess

    # 获取音色库路径
    soundfont = self.soundfont_path

    # 构建命令
    cmd = [
        "fluidsynth",
        "-ni",              # 非交互模式
        soundfont,          # 音色库
        midi_path,          # 输入MIDI
        "-F", output_path,  # 输出WAV
        "-r", "44100",      # 采样率
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"FluidSynth failed: {result.stderr}")

    return output_path
```

## 常见问题

**Q: FluidSynth 安装成功但没声音？**
A: 确认 `.sf2` 音色库文件存在且路径正确。

**Q: 报错 "fluidsynth: command not found"？**
A: 确保已安装 FluidSynth，并将其添加到系统 PATH 环境变量。

**Q: 渲染出来的音频质量不好？**
A: 试试更高质量的音色库（如 Timbres of Heaven，500MB）。

**Q: 能不能不用 FluidSynth？**
A: 可以用在线 API 如 Soundtrap，或自己写一个简单的 WebAudio 页面在浏览器端渲染。

参考 https://zhuanlan.zhihu.com/p/676966597