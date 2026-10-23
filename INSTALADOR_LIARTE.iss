#ifndef AppVersion
  #define AppVersion "5.3.0-rc.1"
#endif
#if VER < EncodeVer(6,3,0)
  #error Utilize Inno Setup 6.3 ou superior para compilar o instalador LIARTE.
#endif
[Setup]
AppId={{67BEFD46-16AD-4EB1-B183-FB8D2A8CA4A2}
AppName=Liarte
AppVersion={#AppVersion}
AppPublisher=LIARTE Metalquímica
DefaultDirName={localappdata}\Programs\LIARTE Desktop
DefaultGroupName=LIARTE
DisableProgramGroupPage=yes
DisableWelcomePage=no
DisableDirPage=yes
DisableReadyPage=yes
ShowLanguageDialog=no
UsePreviousAppDir=yes
UsePreviousLanguage=yes
UsePreviousTasks=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=instalador
OutputBaseFilename=LIARTE_Desktop_{#AppVersion}_Setup
SetupIconFile=src\liarte_desktop\assets\liarte.ico
UninstallDisplayIcon={app}\LIARTE_Desktop.exe
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
CloseApplications=yes
CloseApplicationsFilter=LIARTE_Desktop.exe
RestartApplications=no
AppMutex=Local\LIARTE.Desktop.Running
SetupMutex=Local\LIARTE.Desktop.Setup
SetupLogging=yes
VersionInfoVersion=5.3.0.10
Uninstallable=yes

[Languages]
Name: brazilianportuguese; MessagesFile: compiler:Languages\BrazilianPortuguese.isl

[Messages]
brazilianportuguese.WelcomeLabel1=Liarte
brazilianportuguese.WelcomeLabel2=O aplicativo será preparado para o seu usuário, com atalhos na Área de Trabalho e no menu Iniciar.%n%nTudo o que você precisa para abrir a LIARTE já está incluído. Seus relatórios e preferências serão mantidos nas atualizações.%n%nClique em Instalar para continuar.
brazilianportuguese.FinishedHeadingLabel=Liarte está pronto
brazilianportuguese.FinishedLabelNoIcons=Você já pode abrir o aplicativo pelos atalhos na Área de Trabalho e no menu Iniciar.

[Files]
Source: "dist\LIARTE_Desktop\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\LIARTE Desktop"; Filename: "{app}\LIARTE_Desktop.exe"; WorkingDir: "{app}"; IconFilename: "{app}\LIARTE_Desktop.exe"; AppUserModelID: "LIARTE.Desktop"
Name: "{autoprograms}\LIARTE Desktop\Análise de importações"; Filename: "{app}\LIARTE_Desktop.exe"; WorkingDir: "{app}"; IconFilename: "{app}\LIARTE_Desktop.exe"; AppUserModelID: "LIARTE.Desktop"
Name: "{autoprograms}\LIARTE Desktop\Desinstalar"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\LIARTE_Desktop.exe"; Description: "Abrir Liarte"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpWelcome then
    WizardForm.NextButton.Caption := SetupMessage(msgButtonInstall);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if not UninstallSilent then
    begin
      if MsgBox('O aplicativo foi removido. Deseja também apagar o cache, os diagnósticos e as preferências deste aplicativo?' + #13#10 + #13#10 + 'Se escolher Não, esses dados serão preservados. Os relatórios exportados serão mantidos em ambas as opções.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        DelTree(ExpandConstant('{localappdata}\LIARTE\LIARTE Desktop'), True, True, True);
        RegDeleteKeyIncludingSubkeys(HKCU, 'Software\LIARTE\LIARTE Desktop');
      end;
    end;
  end;
end;
