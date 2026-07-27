#define MyAppName "Tang Primer FPGA Studio"
#ifndef MyAppVersion
  #define MyAppVersion "1.2.0"
#endif
#define MyAppPublisher "Tang Primer FPGA Studio contributors"
#define MyAppURL "https://github.com/atmarachchige0081/Tang-Primer-20K-FPGA-Studio"
#define MyAppExeName "TangPrimerFPGAStudio.exe"

[Setup]
AppId={{68DF41F4-CE6D-4C47-BDA8-F6F61D619408}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\Tang Primer FPGA Studio
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\payload\workspace\LICENSE
OutputDir=..\dist
OutputBaseFilename=TangPrimerFPGAStudio-Setup-{#MyAppVersion}
SetupIconFile=..\assets\TangPrimerFPGAStudio.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={#MyAppVersion}.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} installer
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoCopyright=MIT licensed

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: checkedonce
Name: "toolchain"; Description: "Install or verify the pinned FPGA toolchain (recommended)"; GroupDescription: "FPGA dependencies:"; Flags: checkedonce
Name: "jtagdriver"; Description: "Open the guided JTAG Interface 0 driver tool after setup"; GroupDescription: "Hardware setup:"; Flags: unchecked

[Files]
Source: "..\build\app-dist\TangPrimerFPGAStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "C:\fpga-tools\zadig-2.9.exe"; Description: "Configure JTAG Interface 0 with WinUSB"; Flags: postinstall nowait skipifsilent; Tasks: jtagdriver; Check: FileExists('C:\fpga-tools\zadig-2.9.exe')
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: postinstall nowait skipifsilent runasoriginaluser

[Code]
function InitializeSetup(): Boolean;
var
  FreeMB, TotalMB: Cardinal;
begin
  Result := True;
  if not IsWin64 then
  begin
    MsgBox('{#MyAppName} requires 64-bit Windows 10 or Windows 11.', mbError, MB_OK);
    Result := False;
    exit;
  end;

  if GetSpaceOnDisk(ExpandConstant('{sd}\'), True, FreeMB, TotalMB) and (FreeMB < 4096) then
  begin
    MsgBox('At least 4 GB of free space is required for the IDE and FPGA toolchain.', mbError, MB_OK);
    Result := False;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  PowerShellPath, ScriptPath, Parameters: String;
  ResultCode: Integer;
begin
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('toolchain') then
  begin
    WizardForm.StatusLabel.Caption :=
      'Installing and verifying the FPGA toolchain. This can take several minutes...';
    PowerShellPath := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
    ScriptPath := ExpandConstant(
      '{app}\internal\workspace-template\scripts\setup-toolchain.ps1');
    Parameters := '-NoProfile -ExecutionPolicy Bypass -File "' + ScriptPath +
      '" -SkipVsCodeExtension';

    if not Exec(PowerShellPath, Parameters, ExpandConstant('{app}'), SW_SHOW,
      ewWaitUntilTerminated, ResultCode) then
    begin
      MsgBox('Windows could not start the FPGA dependency installer. ' +
        'The IDE was installed; use Tools > Install/verify toolchain to retry.',
        mbError, MB_OK);
    end
    else if ResultCode <> 0 then
    begin
      MsgBox('The FPGA dependency installation returned error code ' +
        IntToStr(ResultCode) + '. The IDE was installed; check your network ' +
        'connection and use Tools > Install/verify toolchain to retry.',
        mbError, MB_OK);
    end;
  end;
end;
