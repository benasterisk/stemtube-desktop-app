; NSIS hooks for the StemTube Desktop installer.
;
; Why this file exists: the Tauri shell is a light installer. Everything that
; makes the app work — the Python engine (several GB), the database, the
; downloaded library — arrives AFTER installation, so the generated uninstaller
; knows nothing about it. It deletes stemtube-desktop.exe, then calls
; `RMDir "$INSTDIR"` without /r, which silently does nothing because the
; directory still holds the engine. The user is left with a multi-GB folder and
; an app that still looks installed.
;
; PREUNINSTALL removes what the shell downloaded into $INSTDIR.
; POSTUNINSTALL removes the per-user data, but ONLY when the user ticked the
; "delete application data" box the uninstaller already offers ($DeleteAppData).
; Their extracted stems and library are not ours to throw away by default.

!macro NSIS_HOOK_PREUNINSTALL
  DetailPrint "Removing the downloaded engine..."
  ; Installed by the shell on first run, not by this installer.
  RMDir /r "$INSTDIR\stemtube-backend-standard"
  RMDir /r "$INSTDIR\stemtube-backend-friend"
  ; Runtime leftovers that would keep $INSTDIR non-empty.
  Delete "$INSTDIR\tauri-shell.log"
  Delete "$INSTDIR\*.log"
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  ; $INSTDIR may still exist if anything above was locked; take it whole.
  ; Guarded on $UpdateMode: an update reinstalls into the same directory, and
  ; wiping it there would delete the new build.
  ${If} $UpdateMode <> 1
    RMDir /r "$INSTDIR"
  ${EndIf}

  ; Only when the user ticked the box the uninstaller already shows, and never
  ; during an update. Their library and extracted stems live here.
  ${If} $DeleteAppDataCheckboxState = 1
  ${AndIf} $UpdateMode <> 1
    DetailPrint "Removing application data..."
    RMDir /r "$LOCALAPPDATA\${PRODUCTNAME}"
  ${EndIf}
!macroend
