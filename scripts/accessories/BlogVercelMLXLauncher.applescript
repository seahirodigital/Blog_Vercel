on open location launcherURL
    try
        set launcherScript to "/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/accessories/macos_launcher.py"
        set terminalCommand to do shell script "/usr/bin/python3 " & quoted form of launcherScript & " --print-command " & quoted form of launcherURL
        tell application "Terminal"
            activate
            do script terminalCommand
        end tell
    on error errorMessage
        display dialog "MLXターミナルを起動できませんでした。" & return & errorMessage buttons {"閉じる"} default button "閉じる" with icon stop
    end try
end open location
