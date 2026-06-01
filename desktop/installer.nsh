; 引入 LogicLib 以支持 ${If}/${EndIf} 等条件判断宏
!include "LogicLib.nsh"
!include "nsDialogs.nsh"

; ============================================
; 解压性能优化：增大文件 I/O 缓冲区
; ============================================
; NSIS 默认 FileBufSize = 64KB，对于包含大量
; 小文件（Python venv 可能有数万个文件）的安装包，
; 增大 buffer 可以显著减少磁盘 I/O 次数。
; 值为 MB 单位，最大支持 128。
FileBufSize 128

; ============================================
; 安装自定义：自动卸载旧版本，保护用户数据
; ============================================
!macro customInstall
  ; 读取旧版本安装路径
  ReadRegStr $R0 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MamboChat" "UninstallString"
  ${If} $R0 != ""
    DetailPrint "正在卸载旧版本..."

    ; 先关闭正在运行的 MamboChat 进程，避免文件被锁定
    nsExec::ExecToLog 'taskkill /F /IM MamboChat.exe'

    ; 静默卸载旧版本（/S），使用 _?=$INSTDIR 确保卸载程序使用当前安装目录
    ExecWait '"$R0" /S _?=$INSTDIR'

    ; 等待卸载完成，确保进程已完全释放文件
    Sleep 1000
  ${EndIf}

  ; ============================================
  ; 安装时解压 Python 运行时（避免首次启动等待）
  ; ============================================
  StrCpy $0 "$INSTDIR\resources\runtime"
  IfFileExists "$0\python.tar" 0 extractSkip
    DetailPrint "正在解压 Python 运行时，请稍候..."
    ; Windows 10 17063+ 内置 tar.exe，位于 System32
    nsExec::ExecToLog '"$SYSDIR\tar.exe" -xf "$0\python.tar" -C "$0"'
    Pop $1
    ${If} $1 == 0
      ; 解压成功：删除 tar、写入戳记
      Delete "$0\python.tar"
      FileOpen $2 "$0\python\.extraction-ok" w
      FileWrite $2 "${__DATE__} ${__TIME__}$\r$\n"
      FileClose $2
      DetailPrint "Python 运行时安装完成"
    ${Else}
      ; 解压失败：保留 python.tar，应用首次启动兜底解压
      DetailPrint "Python 运行时解压失败（错误码: $1），将在首次启动时自动解压"
    ${EndIf}
  extractSkip:
!macroend

; ============================================
; 以下代码仅在构建卸载器时编译，避免安装器构建时报 warning 6020
; ============================================
!ifdef BUILD_UNINSTALLER

; 自定义页面变量（使用 Mambo 前缀避免冲突）
Var MamboDialog
Var MamboCheckbox
Var MamboDeleteData
Var MamboLangZh

; --- 页面创建：用 nsDialogs 构建自定义 UI ---
Function un.DataPageCreate
  ; 静默模式下跳过此页面
  ${If} ${Silent}
    Abort
  ${EndIf}

  nsDialogs::Create 1018
  Pop $MamboDialog

  ${If} $MamboDialog == error
    Abort
  ${EndIf}

  ; 检测系统语言，决定显示中文还是英文
  ReadRegStr $0 HKCU "Control Panel\International" "LocaleName"
  StrCpy $MamboLangZh "0"
  ${If} $0 != ""
    StrCpy $2 $0 2
    ${If} $2 == "zh"
      StrCpy $MamboLangZh "1"
    ${EndIf}
  ${EndIf}

  ; 默认不删除用户数据
  StrCpy $MamboDeleteData "0"

  ${If} $MamboLangZh == "1"
    ${NSD_CreateLabel} 0 0 100% 20u "是否删除用户数据？"
    Pop $0
    ${NSD_CreateLabel} 0 30u 100% 60u "⚠ 如果勾选，会话历史记录、数据库及上传文件将被永久删除！$\r$\n$\r$\n如需备份数据，请提前复制以下目录：$\r$\n%APPDATA%\mambochat-desktop\data"
    Pop $0
    ${NSD_CreateCheckbox} 0 95u 100% 12u "删除用户数据（会话历史、数据库、上传文件）"
    Pop $MamboCheckbox
  ${Else}
    ${NSD_CreateLabel} 0 0 100% 20u "Delete user data?"
    Pop $0
    ${NSD_CreateLabel} 0 30u 100% 60u "⚠ If checked, session history, database, and uploaded files will be permanently deleted!$\r$\n$\r$\nTo back up your data, copy the following directory beforehand:$\r$\n%APPDATA%\mambochat-desktop\data"
    Pop $0
    ${NSD_CreateCheckbox} 0 95u 100% 12u "Delete user data (session history, database, uploaded files)"
    Pop $MamboCheckbox
  ${EndIf}

  nsDialogs::Show
FunctionEnd

; --- 页面离开：读取复选框状态 ---
Function un.DataPageLeave
  ${NSD_GetState} $MamboCheckbox $0
  ${If} $0 == ${BST_CHECKED}
    StrCpy $MamboDeleteData "1"
  ${Else}
    StrCpy $MamboDeleteData "0"
  ${EndIf}
FunctionEnd

; --- 定义 customUninstallPage 宏（electron-builder 在 assistedInstaller.nsh 中调用） ---
; 注意：不能在此宏内用 UninstPage，因为 electron-builder 的模板已管理页面顺序。
;       但 electron-builder 只检查宏是否定义，不检查其内容。
;       所以我们在此宏内直接插入 UninstPage，它会按照声明顺序插入。
!macro customUninstallPage
  UninstPage custom un.DataPageCreate un.DataPageLeave
!macroend

; --- 卸载时根据复选框选择处理数据 ---
!macro customUnInstall
  ${If} $MamboDeleteData == "1"
    RMDir /r "$APPDATA\mambochat-desktop"
  ${EndIf}
!macroend

!endif ; BUILD_UNINSTALLER
