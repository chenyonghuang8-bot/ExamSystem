# 题境 移动端（Capacitor：Android + iPad）

App 内置前端页面，数据和账号都在你自己的题境服务器（Mac Mini）上。iOS 版**只支持 iPad**（横竖屏都行）。

## 准备
- Node.js 18+（建议 20）
- Android：Android Studio（自带 JDK 17+ 和 Android SDK）
- iPad：一台 Mac + Xcode 15+、CocoaPods（`sudo gem install cocoapods` 或 `brew install cocoapods`）
- 服务器已用 `docker compose up -d --build` 跑起来，手机/iPad 和 Mac Mini 连同一个 Wi‑Fi

## 编译安卓 APK
```bash
cd ExamSystem/mobile
npm install
npm run build        # 把 ../frontend 复制到 www/
npx cap sync
npx cap open android # 用 Android Studio 打开，点 ▶ 运行或 Build > Build APK(s)
```
或者命令行：
```bash
cd android && ./gradlew assembleDebug
# 产物：android/app/build/outputs/apk/debug/app-debug.apk，发到手机安装即可
```

## 编译 iPad 版
```bash
cd ExamSystem/mobile
npm install && npm run build && npx cap sync ios
npx cap open ios     # 打开 Xcode
```
1. Xcode 左侧选 App 工程 → Signing & Capabilities → Team 选你的 Apple ID（Xcode > Settings > Accounts 里登录，免费账号即可）。
2. 若提示 Bundle Identifier 冲突，把 `com.tijing.app` 改成独一无二的，如 `com.你的名字.tijing`。
3. iPad 用数据线连 Mac，顶部选中你的 iPad，点 ▶ 运行。
4. 第一次打开：iPad 设置 → 通用 → VPN与设备管理 → 信任你的开发者证书；iPadOS 16+ 还需打开 设置 → 隐私与安全性 → 开发者模式。
5. 免费 Apple ID 签名的 App **7 天后失效**，到期后连上 Mac 在 Xcode 再点一次 ▶ 即可（数据在服务器上，不会丢）。付费开发者账号（99 美元/年）有效期 1 年。

首次连接局域网时 iPad 会弹出“允许查找本地网络设备”，请点**允许**。

## 设置服务器地址
- 第一次打开 App 会出现「服务器地址」页面，填 `http://你Mac的IP:8000`（Mac 上 系统设置 → Wi‑Fi → 详细信息 可查 IP），点「测试并保存」后登录。
- 以后可在「我的 → 服务器地址」修改。
- 建议在路由器里给 Mac Mini 固定 IP，避免地址变化。

## 更新
服务器前端更新后，`git pull` → `npm run build && npx cap sync` → 重新编译安装。

## 图标（可选）
`assets/icon.png` 使用的是题境图标，运行 `npm run assets` 可自动生成各尺寸 App 图标和启动图（需联网下载 @capacitor/assets）。
