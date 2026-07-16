# FluxBot 安装 / 分发说明

## 发给新电脑（你要的方式）

桌面已有 **单个安装包**：

### `FluxBot-Setup.exe`（约 73 MB）

1. 用微信/网盘/U盘 发给对方 Windows 电脑  
2. 对方 **双击 `FluxBot-Setup.exe`**  
3. 点 **「安装」**  
4. 自动装到：`C:\Users\对方用户名\AppData\Local\FluxBot`  
5. 自动生成桌面快捷方式 **FluxBot**  
6. 可选「立即启动」  

**对方电脑不需要安装 Python，也不需要源码文件夹。**

---

## 本机重新生成安装包

若你改了程序，要再打安装包：

1. 双击 `build.bat`（更新程序本体）  
2. 双击 `make_setup.bat`（生成 `FluxBot-Setup.exe`）  
3. 安装包会出现在：  
   - 桌面：`FluxBot-Setup.exe`  
   - 项目：`dist\FluxBot-Setup.exe`

---

## 注意

| 项 | 说明 |
|----|------|
| 杀毒软件 | 未做微软签名，可能提示未知发布者 → 选「仍要运行」 |
| 系统 | Windows 10/11 64 位 |
| 密钥 | 每人填自己的币安 API；重装会尽量保留已有 `.env` |
| 风险 | 合约可亏光，软件不保证盈利 |

---

## 卸载

1. 删桌面 `FluxBot` 快捷方式  
2. 删文件夹：`%LOCALAPPDATA%\FluxBot`  
3. 安装包本身可删，不影响已安装程序  
