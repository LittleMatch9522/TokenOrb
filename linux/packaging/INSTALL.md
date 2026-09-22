# TokenOrb Linux 安装

## Debian/Ubuntu

```bash
sudo apt install ./TokenOrb-Linux-x86_64.deb
```

## Fedora/RHEL/openSUSE

```bash
sudo dnf install ./TokenOrb-Linux-x86_64.rpm
```

openSUSE 也可以使用：

```bash
sudo zypper install ./TokenOrb-Linux-x86_64.rpm
```

## AppImage

```bash
chmod +x TokenOrb-Linux-x86_64.AppImage
./TokenOrb-Linux-x86_64.AppImage
```

安装包提供桌面菜单、侧边栏和托盘图标。实时额度需要本机已有可用的本地服务；没有实时连接时，应用会尝试读取本地会话快照。
