#!/bin/bash

set -euo pipefail

SOURCE_SCRIPT="/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/accessories/BlogVercelMLXLauncher.applescript"
APP_DIR="/Users/user/Applications"
APP_PATH="/Users/user/Applications/Blog Vercel MLX Launcher.app"
INFO_PLIST="/Users/user/Applications/Blog Vercel MLX Launcher.app/Contents/Info.plist"
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"

echo "=== Blog Vercel MLXターミナルランチャー ==="
echo "インストール先: ${APP_PATH}"

if [ ! -f "${SOURCE_SCRIPT}" ]; then
  echo "エラー: ランチャーソースが見つかりません: ${SOURCE_SCRIPT}"
  exit 1
fi

/bin/mkdir -p "${APP_DIR}"
/usr/bin/osacompile -o "${APP_PATH}" "${SOURCE_SCRIPT}"
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier com.blogvercel.mlx-launcher" "${INFO_PLIST}" >/dev/null 2>&1 \
  || /usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string com.blogvercel.mlx-launcher" "${INFO_PLIST}"
/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName Blog Vercel MLX Launcher" "${INFO_PLIST}" >/dev/null 2>&1 \
  || /usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string Blog Vercel MLX Launcher" "${INFO_PLIST}"
/usr/libexec/PlistBuddy -c "Set :LSBackgroundOnly true" "${INFO_PLIST}" >/dev/null 2>&1 \
  || /usr/libexec/PlistBuddy -c "Add :LSBackgroundOnly bool true" "${INFO_PLIST}"
/usr/libexec/PlistBuddy -c "Delete :CFBundleURLTypes" "${INFO_PLIST}" >/dev/null 2>&1 || true
/usr/libexec/PlistBuddy -c "Add :CFBundleURLTypes array" "${INFO_PLIST}"
/usr/libexec/PlistBuddy -c "Add :CFBundleURLTypes:0 dict" "${INFO_PLIST}"
/usr/libexec/PlistBuddy -c "Add :CFBundleURLTypes:0:CFBundleURLName string Blog Vercel MLX" "${INFO_PLIST}"
/usr/libexec/PlistBuddy -c "Add :CFBundleURLTypes:0:CFBundleURLSchemes array" "${INFO_PLIST}"
/usr/libexec/PlistBuddy -c "Add :CFBundleURLTypes:0:CFBundleURLSchemes:0 string blogvercel-mlx" "${INFO_PLIST}"
/usr/libexec/PlistBuddy -c "Set :NSAppleEventsUsageDescription Blog VercelからMLX処理を開始するためTerminalを開きます。" "${INFO_PLIST}" >/dev/null 2>&1 \
  || /usr/libexec/PlistBuddy -c "Add :NSAppleEventsUsageDescription string Blog VercelからMLX処理を開始するためTerminalを開きます。" "${INFO_PLIST}"
# osacompileの汎用テンプレートに含まれる未使用権限の説明を除き、Terminal制御用のApple Eventsだけを残す。
for UNUSED_PERMISSION in \
  NSHomeKitUsageDescription \
  NSAppleMusicUsageDescription \
  NSCalendarsUsageDescription \
  NSSiriUsageDescription \
  NSCameraUsageDescription \
  NSMicrophoneUsageDescription \
  NSRemindersUsageDescription \
  NSContactsUsageDescription \
  NSPhotoLibraryUsageDescription \
  NSSystemAdministrationUsageDescription
do
  /usr/libexec/PlistBuddy -c "Delete :${UNUSED_PERMISSION}" "${INFO_PLIST}" >/dev/null 2>&1 || true
done
/usr/bin/codesign --force --deep --sign - "${APP_PATH}"
"${LSREGISTER}" -f "${APP_PATH}"
/usr/bin/touch "${APP_PATH}"

echo "インストールが完了しました。"
echo "Blog Vercelの『MLXで作成』から、Chromeの確認画面で『Blog Vercel MLX Launcher.appを開く』を選択してください。"
