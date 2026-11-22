; Installer for the portable tree produced by package.sh.
; makensis -DSRC=C:\kb\dist\KiCad-10.0.8-qol-win64 -DOUTFILE=C:\kb\dist\KiCad-10.0.8-qol-win64-setup.exe kicad-qol.nsi
Unicode true
SetCompressor /SOLID lzma
!include "MUI2.nsh"
!include "x64.nsh"

!define APPNAME "KiCad 10.0.8 (QOL patched)"
!define REGKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\KiCad-10.0.8-qol"

Name "${APPNAME}"
OutFile "${OUTFILE}"
InstallDir "$PROGRAMFILES64\KiCad-QOL\10.0"
RequestExecutionLevel admin

!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "This build is for 64-bit (x64) Windows only."
    Abort
  ${EndIf}
  SetRegView 64
FunctionEnd

Section "Install"
  SetShellVarContext all
  SetOutPath "$INSTDIR"
  File /r "${SRC}\*.*"
  WriteUninstaller "$INSTDIR\uninstall.exe"
  CreateDirectory "$SMPROGRAMS\${APPNAME}"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\KiCad.lnk" "$INSTDIR\bin\kicad.exe"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\PCB Editor.lnk" "$INSTDIR\bin\pcbnew.exe"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\Schematic Editor.lnk" "$INSTDIR\bin\eeschema.exe"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\Uninstall.lnk" "$INSTDIR\uninstall.exe"
  WriteRegStr HKLM "${REGKEY}" "DisplayName" "${APPNAME}"
  WriteRegStr HKLM "${REGKEY}" "DisplayVersion" "10.0.8"
  WriteRegStr HKLM "${REGKEY}" "Publisher" "KavEn06/QOL-KiCAD (unofficial build)"
  WriteRegStr HKLM "${REGKEY}" "DisplayIcon" "$INSTDIR\bin\kicad.exe"
  WriteRegStr HKLM "${REGKEY}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegDWORD HKLM "${REGKEY}" "NoModify" 1
  WriteRegDWORD HKLM "${REGKEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  SetShellVarContext all
  SetRegView 64
  RMDir /r "$SMPROGRAMS\${APPNAME}"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKLM "${REGKEY}"
SectionEnd
