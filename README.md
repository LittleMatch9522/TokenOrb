# TokenOrb v1.6.0

TokenOrb 是一个实时监控本地服务剩余额度的悬浮球小软件。

## Windows 安装

1. 从右侧 Release 下载 `TokenOrb-Windows.msi`（推荐）进行安装，也可直接运行免安装的 `TokenOrb-Windows.exe`。
2. 启动 TokenOrb。
3. TokenOrb 会在配套桌面服务启动时出现，并在服务关闭后退出悬浮球界面。

## macOS 安装

1. 从右侧 Release 下载 `TokenOrb-macOS.dmg`，下载完成后双击打开。
2. 在安装窗口中，将 `TokenOrb` 拖到“Applications（应用程序）”文件夹。请不要直接在 DMG 中运行。
3. 打开 Finder 的“应用程序”文件夹，双击 `TokenOrb`。首次打开时，macOS 会阻止应用运行；看到提示后关闭提示窗口即可。
4. 点击屏幕左上角的苹果菜单，依次打开“系统设置 → 隐私与安全性”。
5. 向下找到“安全性”区域，找到与 `TokenOrb` 相关的拦截提示，点击旁边的放行按钮（通常显示为“仍要打开”），然后使用 Touch ID 或输入 Mac 登录密码，并再次确认打开。
6. 返回“应用程序”文件夹启动 `TokenOrb`。系统会记住这次选择，以后可以直接双击打开。仅第一次安装需要手动允许。

macOS 客户端支持 Apple Silicon 与 Intel、菜单栏、桌面悬浮球、实时额度、外观设置、账号切换重连和进程级跟随本地服务启动/退出。轻量 watcher 在等待期间保留菜单栏诊断入口。

## Linux 安装

Linux 版本提供 Debian/Ubuntu、Fedora/RHEL/openSUSE 和 AppImage 安装包，首版支持 x86_64：

1. Debian/Ubuntu：`sudo apt install ./TokenOrb-Linux-x86_64.deb`
2. Fedora/RHEL：`sudo dnf install ./TokenOrb-Linux-x86_64.rpm`
3. openSUSE：`sudo zypper install ./TokenOrb-Linux-x86_64.rpm`
4. AppImage：执行 `chmod +x TokenOrb-Linux-x86_64.AppImage` 后双击或运行它。

从源码运行时，Ubuntu 可先安装 `python3-pyqt5`，再执行
`./linux/install_linux.sh` 将 TokenOrb 注册到当前用户的应用菜单。

Linux 端通过本地服务接口获取实时额度；如果实时接口暂时不可用，会从
本地会话目录读取快照。可用
`./linux/run_tokenorb.sh --demo` 查看演示悬浮球。

## 界面预览
#### 1. 悬浮球
![orb](./assets/orb.png)
#### 2. 监控界面
![main_screen](./assets/main_screen.png)
#### 3. 右键悬浮球菜单
![right_click_menu](./assets/right_click_menu.png)
#### 4. 自定义悬浮球外观
![customization](./assets/customization.png)

## 功能

- **跟随本地服务启动/退出**
- **实时监控额度、订阅套餐类型、下轮刷新时间**
- **切换本地账号后自动重连并刷新当前账号额度**
- **自定义悬浮球大小、主题颜色、数字样式和 30–180 FPS 动画帧率**
- **显示/隐藏悬浮球**

## 系统要求

- Windows 10 / 11，或 macOS 13 及更新版本
- 已安装并登录配套桌面服务；关闭跟随功能后，也可仅配合本地命令行工具使用
- Windows 版本需要系统自带的 .NET Framework 4.x
- 从源码构建 macOS 版本需要 Apple Command Line Tools
