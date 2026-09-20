; NSIS hooks for the StemTube Desktop installer.
;
; Why this file exists: the Tauri shell is a light installer. Everything that
; makes the app work — the Python engine (several GB), the database, the
; downloaded library — arrives AFTER installation, so the generated uninstaller
; knows nothing about it. It deletes stemtube-desktop.exe, then calls
; `RMDir "$INSTDIR"` without /r, which silently does nothing because the
; directory still holds the engine. The user is left with a multi-GB folder.
;
; Two things have to happen, in this order:
;   1. Stop the Python backend. It can outlive the shell (after an in-app
;      update it restarts itself and the shell loses track of it), and while it
;      runs every file of the venv is locked, so RMDir /r removes nothing.
;   2. Remove what the shell downloaded.
;
; $INSTDIR is also where the user's library lives (downloads\, stemtubes.db).
; That part is only deleted when the user ticks the "delete application data"
; box the uninstaller already shows, or when the library is empty anyway.

!macro NSIS_HOOK_PREUNINSTALL
  ${If} $UpdateMode <> 1
    DetailPrint "Stopping the StemTube engine..."
    ; Scoped to the engine folders: with `_?=` the uninstaller itself runs from
    ; $INSTDIR and must not be caught. /T also takes the base interpreter that
    ; venv\Scripts\python.exe spawns, which lives outside $INSTDIR.
    nsExec::Exec `powershell -NoProfile -NonInteractive -Command "Get-CimInstance Win32_Process | Where-Object { $$_.ExecutablePath -like '$INSTDIR\stemtube-backend-*' } | ForEach-Object { taskkill /F /T /PID $$_.ProcessId }"`
    Pop $0
    ; Give Windows a moment to release the file handles of the killed processes.
    Sleep 1500

    DetailPrint "Removing the downloaded engine..."
    RMDir /r "$INSTDIR\stemtube-backend-standard"
    RMDir /r "$INSTDIR\stemtube-backend-friend"
    ; Re-downloadable or per-session leftovers, never user content.
    RMDir /r "$INSTDIR\models"
    RMDir /r "$INSTDIR\logs"
    RMDir /r "$INSTDIR\flask_session"
    Delete "$INSTDIR\*.log"
    Delete "$INSTDIR\updater_state.json"
    Delete "$INSTDIR\updater_status.json"
  ${EndIf}
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  ${If} $UpdateMode <> 1
    ${If} $DeleteAppDataCheckboxState = 1
      DetailPrint "Removing application data..."
      RMDir /r "$INSTDIR"
    ${Else}
      ; No /r: only succeeds when the library is empty. In that case the
      ; database and settings describe nothing and the whole folder can go.
      RMDir "$INSTDIR\downloads"
      ${IfNot} ${FileExists} "$INSTDIR\downloads\*.*"
        Delete "$INSTDIR\stemtubes.db"
        Delete "$INSTDIR\config.json"
        Delete "$INSTDIR\.secret_key"
      ${EndIf}
      RMDir "$INSTDIR"
    ${EndIf}

    ; Nothing left on disk: drop the install-location key too. Tauri only does
    ; it when the box is ticked, and a stale key makes the next installer greet
    ; the user with "already installed" for an app that is gone.
    ${IfNot} ${FileExists} "$INSTDIR\*.*"
      DeleteRegKey SHCTX "${MANUPRODUCTKEY}"
      DeleteRegKey /ifempty SHCTX "${MANUKEY}"
    ${EndIf}
  ${EndIf}
!macroend
