using System;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Threading;
using System.Diagnostics;
using System.Drawing;
using System.Windows.Forms;
using Microsoft.Win32;

namespace PrahariInstaller
{
    public static class Constants
    {
        public const string APP_NAME = "PRAHARI";
        public const string APP_VERSION = "v1.0.0";
        public const string RELEASE_ZIP_NAME = "PRAHARI-v1.0.0-Windows-x64.zip";
        public const string RELEASE_URL = "https://github.com/anurag-po/SIHprahariDemo/releases/download/v1.0.0/PRAHARI-v1.0.0-Windows-x64.zip";
        public const string CHECKSUM_URL = "https://github.com/anurag-po/SIHprahariDemo/releases/download/v1.0.0/SHA256SUMS.txt";
    }

    static class Program
    {
        [STAThread]
        static void Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            string exeName = Path.GetFileName(Application.ExecutablePath).ToLowerInvariant();
            bool isUninstall = exeName.Contains("uninstall");
            bool isSilent = false;
            string customTarget = null;

            if (args != null && args.Length > 0)
            {
                foreach (string arg in args)
                {
                    if (arg.Equals("/uninstall", StringComparison.OrdinalIgnoreCase) ||
                        arg.Equals("--uninstall", StringComparison.OrdinalIgnoreCase) ||
                        arg.Equals("-u", StringComparison.OrdinalIgnoreCase))
                    {
                        isUninstall = true;
                    }
                    else if (arg.Equals("/silent", StringComparison.OrdinalIgnoreCase) ||
                             arg.Equals("--silent", StringComparison.OrdinalIgnoreCase) ||
                             arg.Equals("-s", StringComparison.OrdinalIgnoreCase) ||
                             arg.Equals("/s", StringComparison.OrdinalIgnoreCase))
                    {
                        isSilent = true;
                    }
                    else if (!arg.StartsWith("/") && !arg.StartsWith("-"))
                    {
                        customTarget = arg.Trim('"');
                    }
                }
            }

            if (isSilent)
            {
                if (isUninstall)
                {
                    InstallerCore.ExecuteUninstall(AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\'));
                }
                else
                {
                    string target = customTarget;
                    if (string.IsNullOrEmpty(target))
                    {
                        target = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), Constants.APP_NAME);
                    }
                    InstallerCore.ExecuteInstall(target, true, true, (s, d, p) => Console.WriteLine("[Setup] " + s + " (" + p + "%)"));
                }
                return;
            }

            if (isUninstall)
            {
                Application.Run(new UninstallerForm());
            }
            else
            {
                Application.Run(new InstallerForm(customTarget));
            }
        }
    }

    public static class InstallerCore
    {
        public static bool IsAdministrator()
        {
            try
            {
                using (WindowsIdentity identity = WindowsIdentity.GetCurrent())
                {
                    WindowsPrincipal principal = new WindowsPrincipal(identity);
                    return principal.IsInRole(WindowsBuiltInRole.Administrator);
                }
            }
            catch
            {
                return false;
            }
        }

        public static string ComputeSha256(string filePath)
        {
            using (SHA256 sha = SHA256.Create())
            {
                using (FileStream fs = File.OpenRead(filePath))
                {
                    byte[] hash = sha.ComputeHash(fs);
                    StringBuilder sb = new StringBuilder();
                    foreach (byte b in hash)
                    {
                        sb.Append(b.ToString("x2"));
                    }
                    return sb.ToString();
                }
            }
        }

        public static void CreateShortcut(string shortcutPath, string targetPath, string workingDir, string description)
        {
            try
            {
                Type shellType = Type.GetTypeFromProgID("WScript.Shell");
                dynamic shell = Activator.CreateInstance(shellType);
                dynamic shortcut = shell.CreateShortcut(shortcutPath);
                shortcut.TargetPath = targetPath;
                shortcut.WorkingDirectory = workingDir;
                shortcut.Description = description;
                shortcut.Save();
            }
            catch (Exception)
            {
                try
                {
                    string psCommand = string.Format(
                        "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('{0}'); $s.TargetPath = '{1}'; $s.WorkingDirectory = '{2}'; $s.Description = '{3}'; $s.Save()",
                        shortcutPath.Replace("'", "''"),
                        targetPath.Replace("'", "''"),
                        workingDir.Replace("'", "''"),
                        description.Replace("'", "''")
                    );
                    ProcessStartInfo psi = new ProcessStartInfo("powershell.exe", "-NoProfile -Command \"" + psCommand + "\"");
                    psi.CreateNoWindow = true;
                    psi.UseShellExecute = false;
                    Process p = Process.Start(psi);
                    if (p != null) p.WaitForExit();
                }
                catch { }
            }
        }

        public static void RegisterUninstaller(string installPath, string uninstallerPath)
        {
            try
            {
                RegistryKey baseKey = IsAdministrator() ? Registry.LocalMachine : Registry.CurrentUser;
                using (RegistryKey key = baseKey.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\PRAHARI"))
                {
                    if (key != null)
                    {
                        key.SetValue("DisplayName", "PRAHARI - Mission HAR Space Experiment Assistant");
                        key.SetValue("DisplayVersion", Constants.APP_VERSION.TrimStart('v'));
                        key.SetValue("Publisher", "PRAHARI Mission Team");
                        key.SetValue("InstallLocation", installPath);
                        key.SetValue("UninstallString", "\"" + uninstallerPath + "\"");
                        key.SetValue("DisplayIcon", Path.Combine(installPath, "PRAHARI.exe") + ",0");
                        key.SetValue("NoModify", 1, RegistryValueKind.DWord);
                        key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
                        key.SetValue("EstimatedSize", 180000, RegistryValueKind.DWord);
                    }
                }
            }
            catch { }
        }

        public static void ExecuteInstall(string finalInstallPath, bool createDesktop, bool createStartMenu, Action<string, string, int> reportProgress)
        {
            // Force TLS 1.2
            ServicePointManager.SecurityProtocol = (SecurityProtocolType)3072 | (SecurityProtocolType)768 | SecurityProtocolType.Tls;

            string tempDir = Path.Combine(Path.GetTempPath(), "PrahariInstaller_" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(tempDir);
            string zipPath = Path.Combine(tempDir, Constants.RELEASE_ZIP_NAME);

            // Step 0: Check for running PRAHARI process
            Process[] running = Process.GetProcessesByName("PRAHARI");
            if (running != null && running.Length > 0)
            {
                throw new Exception("PRAHARI is currently running. Please close running PRAHARI instances and try again.");
            }

            // Step 1: Pre-create writable user data directories (%LOCALAPPDATA%\PRAHARI\...)
            if (reportProgress != null) reportProgress("Preparing user directories...", "%LOCALAPPDATA%\\PRAHARI", 10);
            string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string userDir = Path.Combine(localAppData, Constants.APP_NAME);
            Directory.CreateDirectory(userDir);
            Directory.CreateDirectory(Path.Combine(userDir, "models"));
            Directory.CreateDirectory(Path.Combine(userDir, "logs"));
            Directory.CreateDirectory(Path.Combine(userDir, "recordings"));

            // Step 2: Locate or download package archive
            string localExeDir = AppDomain.CurrentDomain.BaseDirectory;
            string localZip = Path.Combine(localExeDir, Constants.RELEASE_ZIP_NAME);
            string siblingZip = Path.Combine(localExeDir, "..", "release", Constants.RELEASE_ZIP_NAME);
            string localChecksum = Path.Combine(localExeDir, "SHA256SUMS.txt");
            string siblingChecksum = Path.Combine(localExeDir, "..", "release", "SHA256SUMS.txt");
            string checksumContent = "";

            if (File.Exists(localZip))
            {
                if (reportProgress != null) reportProgress("Loading local package...", "Using " + localZip, 25);
                File.Copy(localZip, zipPath, true);
                if (File.Exists(localChecksum))
                {
                    try { checksumContent = File.ReadAllText(localChecksum); } catch { }
                }
            }
            else if (File.Exists(siblingZip))
            {
                if (reportProgress != null) reportProgress("Loading release package...", "Using " + siblingZip, 25);
                File.Copy(siblingZip, zipPath, true);
                if (File.Exists(siblingChecksum))
                {
                    try { checksumContent = File.ReadAllText(siblingChecksum); } catch { }
                }
            }
            else
            {
                if (reportProgress != null) reportProgress("Downloading application package...", "Connecting to GitHub Releases...", 15);
                using (WebClient client = new WebClient())
                {
                    client.Headers.Add("User-Agent", "PRAHARI-Bootstrapper-Installer");
                    client.DownloadProgressChanged += (s, ev) =>
                    {
                        int pct = 15 + (int)(ev.ProgressPercentage * 0.4);
                        if (reportProgress != null)
                        {
                            reportProgress(
                                string.Format("Downloading PRAHARI ({0} MB / {1} MB)...", (ev.BytesReceived / 1048576.0).ToString("0.0"), (ev.TotalBytesToReceive / 1048576.0).ToString("0.0")),
                                "HTTPS Download from GitHub Releases",
                                pct
                            );
                        }
                    };

                    try
                    {
                        client.DownloadFile(new Uri(Constants.RELEASE_URL), zipPath);
                    }
                    catch (Exception dlEx)
                    {
                        throw new Exception("Unable to download release package over HTTPS. Please check your internet connection or place " + Constants.RELEASE_ZIP_NAME + " next to this installer.\nError: " + dlEx.Message);
                    }

                    try
                    {
                        checksumContent = client.DownloadString(new Uri(Constants.CHECKSUM_URL));
                    }
                    catch { }
                }
            }

            // Step 3: Checksum integrity verification
            if (reportProgress != null) reportProgress("Verifying package integrity...", "Calculating SHA-256 checksum...", 55);
            string calculatedHash = ComputeSha256(zipPath).ToLowerInvariant();

            if (!string.IsNullOrEmpty(checksumContent))
            {
                string expectedHash = "";
                foreach (string line in checksumContent.Split(new char[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries))
                {
                    string trimmed = line.Trim();
                    if (trimmed.Contains(Constants.RELEASE_ZIP_NAME) || trimmed.Length >= 64)
                    {
                        string[] parts = trimmed.Split(new char[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries);
                        if (parts.Length > 0 && parts[0].Length == 64)
                        {
                            expectedHash = parts[0].ToLowerInvariant();
                            break;
                        }
                    }
                }

                if (!string.IsNullOrEmpty(expectedHash))
                {
                    if (calculatedHash != expectedHash)
                    {
                        try { File.Delete(zipPath); } catch { }
                        throw new Exception("Installation aborted.\nThe downloaded package failed integrity verification.\nExpected: " + expectedHash + "\nActual: " + calculatedHash);
                    }
                    if (reportProgress != null) reportProgress("Package integrity verified.", "SHA-256: " + calculatedHash.Substring(0, 16) + "... [MATCH]", 65);
                }
            }

            // Step 4: Extract application files with path traversal security
            if (reportProgress != null) reportProgress("Installing application files...", "Extracting to " + finalInstallPath + "...", 70);
            if (!Directory.Exists(finalInstallPath))
            {
                Directory.CreateDirectory(finalInstallPath);
            }

            string fullDestDir = Path.GetFullPath(finalInstallPath);
            using (ZipArchive archive = ZipFile.OpenRead(zipPath))
            {
                foreach (ZipArchiveEntry entry in archive.Entries)
                {
                    string destPath = Path.GetFullPath(Path.Combine(fullDestDir, entry.FullName));
                    if (!destPath.StartsWith(fullDestDir, StringComparison.OrdinalIgnoreCase))
                    {
                        throw new System.Security.SecurityException("Archive contains illegal path traversal entry: " + entry.FullName);
                    }

                    if (string.IsNullOrEmpty(entry.Name))
                    {
                        Directory.CreateDirectory(destPath);
                    }
                    else
                    {
                        Directory.CreateDirectory(Path.GetDirectoryName(destPath));
                        entry.ExtractToFile(destPath, true);
                    }
                }
            }

            // Flatten nested single folder if zipped root
            string nestedExe = Path.Combine(finalInstallPath, Constants.APP_NAME, "PRAHARI.exe");
            if (File.Exists(nestedExe))
            {
                string nestedDir = Path.Combine(finalInstallPath, Constants.APP_NAME);
                foreach (string item in Directory.GetFileSystemEntries(nestedDir))
                {
                    string dest = Path.Combine(finalInstallPath, Path.GetFileName(item));
                    if (Directory.Exists(item))
                    {
                        if (Directory.Exists(dest)) Directory.Delete(dest, true);
                        Directory.Move(item, dest);
                    }
                    else
                    {
                        if (File.Exists(dest)) File.Delete(dest);
                        File.Move(item, dest);
                    }
                }
                Directory.Delete(nestedDir, true);
            }

            // Step 5: Install Uninstaller executable & register with Windows
            if (reportProgress != null) reportProgress("Registering uninstaller...", "Configuring Windows Apps/Programs...", 85);
            string uninstallerPath = Path.Combine(finalInstallPath, "uninstall.exe");
            try
            {
                File.Copy(Application.ExecutablePath, uninstallerPath, true);
            }
            catch { }

            RegisterUninstaller(finalInstallPath, uninstallerPath);

            // Step 6: Create Desktop & Start Menu Shortcuts
            if (reportProgress != null) reportProgress("Creating shortcuts...", "Registering Desktop and Start Menu entries...", 92);
            string mainExe = Path.Combine(finalInstallPath, "PRAHARI.exe");

            if (createDesktop)
            {
                string desktopPath = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                string shortcutPath = Path.Combine(desktopPath, "PRAHARI.lnk");
                CreateShortcut(shortcutPath, mainExe, finalInstallPath, "PRAHARI - Mission HAR Space Experiment Assistant");
            }

            if (createStartMenu)
            {
                string startMenu = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.StartMenu), "Programs", Constants.APP_NAME);
                Directory.CreateDirectory(startMenu);
                string shortcutPath = Path.Combine(startMenu, "PRAHARI.lnk");
                CreateShortcut(shortcutPath, mainExe, finalInstallPath, "PRAHARI - Mission HAR Space Experiment Assistant");

                string uninstallShortcut = Path.Combine(startMenu, "Uninstall PRAHARI.lnk");
                CreateShortcut(uninstallShortcut, uninstallerPath, finalInstallPath, "Uninstall PRAHARI");
            }

            // Cleanup temp
            try { Directory.Delete(tempDir, true); } catch { }

            if (reportProgress != null) reportProgress("Installation Completed Successfully!", "Ready at: " + finalInstallPath, 100);
        }

        public static void ExecuteUninstall(string installDir)
        {
            // 1. Terminate running PRAHARI processes
            try
            {
                foreach (Process p in Process.GetProcessesByName("PRAHARI"))
                {
                    try { p.Kill(); } catch { }
                }
            }
            catch { }

            // 2. Remove Shortcuts
            try
            {
                string desktopLnk = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "PRAHARI.lnk");
                if (File.Exists(desktopLnk)) File.Delete(desktopLnk);

                string startMenu = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.StartMenu), "Programs", Constants.APP_NAME);
                if (Directory.Exists(startMenu)) Directory.Delete(startMenu, true);
            }
            catch { }

            // 3. Remove Windows Registry Uninstall entries
            try
            {
                Registry.LocalMachine.DeleteSubKeyTree(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\PRAHARI", false);
                Registry.CurrentUser.DeleteSubKeyTree(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\PRAHARI", false);
            }
            catch { }

            // 4. Schedule deletion of installed application files after uninstaller exits
            // Do NOT delete %LOCALAPPDATA%\PRAHARI (preserve user logs, recordings, models)
            string scriptCmd = string.Format(
                "/c ping 127.0.0.1 -n 2 > nul & rmdir /s /q \"{0}\"",
                installDir
            );

            ProcessStartInfo psi = new ProcessStartInfo("cmd.exe", scriptCmd)
            {
                CreateNoWindow = true,
                UseShellExecute = false
            };
            Process.Start(psi);
        }
    }

    public class InstallerForm : Form
    {
        private Label lblTitle;
        private Label lblSubtitle;
        private Label lblInstallDir;
        private TextBox txtInstallDir;
        private Button btnBrowse;
        private Button btnInstall;
        private ProgressBar progressBar;
        private Label lblStatus;
        private Label lblDetails;
        private CheckBox chkLaunch;
        private CheckBox chkDesktopShortcut;
        private CheckBox chkStartMenuShortcut;
        private Panel pnlHeader;
        private Panel pnlContent;
        private Panel pnlFooter;

        private bool isInstalling = false;
        private string finalInstallPath = "";

        public InstallerForm(string customPath)
        {
            InitializeComponent();
            if (!string.IsNullOrEmpty(customPath))
            {
                txtInstallDir.Text = customPath;
            }
        }

        private void InitializeComponent()
        {
            this.Text = "PRAHARI Setup — Mission HAR Assistant " + Constants.APP_VERSION;
            this.Size = new Size(580, 440);
            this.StartPosition = FormStartPosition.CenterScreen;
            this.FormBorderStyle = FormBorderStyle.FixedDialog;
            this.MaximizeBox = false;
            this.BackColor = Color.FromArgb(15, 17, 23);
            this.ForeColor = Color.FromArgb(230, 237, 243);
            this.Font = new Font("Segoe UI", 9F, FontStyle.Regular, GraphicsUnit.Point);

            // Header
            pnlHeader = new Panel
            {
                Dock = DockStyle.Top,
                Height = 70,
                BackColor = Color.FromArgb(22, 27, 34)
            };

            lblTitle = new Label
            {
                Text = "PRAHARI — Mission HAR Space Experiment Assistant",
                Font = new Font("Segoe UI", 11.5F, FontStyle.Bold),
                ForeColor = Color.FromArgb(88, 166, 255),
                Location = new Point(16, 12),
                AutoSize = true
            };
            pnlHeader.Controls.Add(lblTitle);

            lblSubtitle = new Label
            {
                Text = "Self-Contained Windows Desktop Application Installer " + Constants.APP_VERSION,
                Font = new Font("Segoe UI", 8.5F),
                ForeColor = Color.FromArgb(139, 148, 158),
                Location = new Point(18, 38),
                AutoSize = true
            };
            pnlHeader.Controls.Add(lblSubtitle);
            this.Controls.Add(pnlHeader);

            // Content Panel
            pnlContent = new Panel
            {
                Location = new Point(16, 80),
                Size = new Size(532, 260),
                BackColor = Color.Transparent
            };

            lblInstallDir = new Label
            {
                Text = "Install Location:",
                Location = new Point(0, 8),
                AutoSize = true,
                Font = new Font("Segoe UI", 9F, FontStyle.Bold)
            };
            pnlContent.Controls.Add(lblInstallDir);

            // Canonical install location: C:\Program Files\PRAHARI
            string defaultPath = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
                Constants.APP_NAME
            );

            txtInstallDir = new TextBox
            {
                Text = defaultPath,
                Location = new Point(0, 30),
                Width = 430,
                BackColor = Color.FromArgb(13, 17, 23),
                ForeColor = Color.White,
                BorderStyle = BorderStyle.FixedSingle,
                Font = new Font("Segoe UI", 9F)
            };
            pnlContent.Controls.Add(txtInstallDir);

            btnBrowse = new Button
            {
                Text = "Browse...",
                Location = new Point(440, 28),
                Width = 85,
                Height = 26,
                FlatStyle = FlatStyle.Flat,
                BackColor = Color.FromArgb(33, 38, 45),
                ForeColor = Color.White,
                Cursor = Cursors.Hand
            };
            btnBrowse.FlatAppearance.BorderColor = Color.FromArgb(48, 54, 61);
            btnBrowse.Click += (s, e) =>
            {
                using (FolderBrowserDialog fbd = new FolderBrowserDialog())
                {
                    fbd.SelectedPath = txtInstallDir.Text;
                    if (fbd.ShowDialog() == DialogResult.OK)
                    {
                        txtInstallDir.Text = fbd.SelectedPath;
                    }
                }
            };
            pnlContent.Controls.Add(btnBrowse);

            chkDesktopShortcut = new CheckBox
            {
                Text = "Create Desktop Shortcut",
                Checked = true,
                Location = new Point(4, 70),
                AutoSize = true
            };
            pnlContent.Controls.Add(chkDesktopShortcut);

            chkStartMenuShortcut = new CheckBox
            {
                Text = "Create Start Menu Shortcut",
                Checked = true,
                Location = new Point(4, 95),
                AutoSize = true
            };
            pnlContent.Controls.Add(chkStartMenuShortcut);

            progressBar = new ProgressBar
            {
                Location = new Point(0, 135),
                Width = 525,
                Height = 20,
                Minimum = 0,
                Maximum = 100,
                Value = 0,
                Visible = false
            };
            pnlContent.Controls.Add(progressBar);

            lblStatus = new Label
            {
                Text = "Ready to install. Click 'Install PRAHARI' to begin.",
                Location = new Point(0, 165),
                Width = 525,
                ForeColor = Color.FromArgb(0, 230, 118),
                Font = new Font("Segoe UI", 9F, FontStyle.Bold)
            };
            pnlContent.Controls.Add(lblStatus);

            lblDetails = new Label
            {
                Text = "Self-contained build with Python runtime, YOLO detector, and MediaPipe tracking.",
                Location = new Point(0, 190),
                Width = 525,
                Height = 40,
                ForeColor = Color.FromArgb(139, 148, 158),
                Font = new Font("Segoe UI", 8F)
            };
            pnlContent.Controls.Add(lblDetails);

            chkLaunch = new CheckBox
            {
                Text = "Launch PRAHARI after installation",
                Checked = true,
                Location = new Point(4, 232),
                AutoSize = true,
                Visible = false,
                Font = new Font("Segoe UI", 9F, FontStyle.Bold),
                ForeColor = Color.FromArgb(88, 166, 255)
            };
            pnlContent.Controls.Add(chkLaunch);

            this.Controls.Add(pnlContent);

            // Footer Panel
            pnlFooter = new Panel
            {
                Dock = DockStyle.Bottom,
                Height = 55,
                BackColor = Color.FromArgb(22, 27, 34)
            };

            btnInstall = new Button
            {
                Text = "Install PRAHARI",
                Location = new Point(415, 12),
                Width = 135,
                Height = 32,
                FlatStyle = FlatStyle.Flat,
                BackColor = Color.FromArgb(35, 134, 54),
                ForeColor = Color.White,
                Font = new Font("Segoe UI", 9.5F, FontStyle.Bold),
                Cursor = Cursors.Hand
            };
            btnInstall.FlatAppearance.BorderSize = 0;
            btnInstall.Click += BtnInstall_Click;
            pnlFooter.Controls.Add(btnInstall);

            this.Controls.Add(pnlFooter);
        }

        private void BtnInstall_Click(object sender, EventArgs e)
        {
            if (btnInstall.Text == "Finish" || btnInstall.Text == "Close")
            {
                if (chkLaunch.Visible && chkLaunch.Checked && !string.IsNullOrEmpty(finalInstallPath))
                {
                    string exePath = Path.Combine(finalInstallPath, "PRAHARI.exe");
                    if (File.Exists(exePath))
                    {
                        ProcessStartInfo psi = new ProcessStartInfo(exePath)
                        {
                            WorkingDirectory = finalInstallPath
                        };
                        Process.Start(psi);
                    }
                }
                Application.Exit();
                return;
            }

            if (isInstalling) return;

            finalInstallPath = txtInstallDir.Text.Trim();
            if (string.IsNullOrEmpty(finalInstallPath))
            {
                MessageBox.Show("Please select a valid installation directory.", "Invalid Path", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            // Check if installing to Program Files without admin rights
            string programFiles = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
            if (finalInstallPath.StartsWith(programFiles, StringComparison.OrdinalIgnoreCase) && !InstallerCore.IsAdministrator())
            {
                DialogResult elevateChoice = MessageBox.Show(
                    "Installing to 'C:\\Program Files\\PRAHARI' requires administrator privileges.\n\n" +
                    "Click OK to restart the installer with administrator permissions via UAC,\n" +
                    "or click Cancel to choose a writable user directory.",
                    "Administrator Privileges Required",
                    MessageBoxButtons.OKCancel,
                    MessageBoxIcon.Information
                );

                if (elevateChoice == DialogResult.OK)
                {
                    try
                    {
                        ProcessStartInfo psi = new ProcessStartInfo
                        {
                            FileName = Application.ExecutablePath,
                            Arguments = "\"" + finalInstallPath + "\"",
                            UseShellExecute = true,
                            Verb = "runas"
                        };
                        Process.Start(psi);
                        Application.Exit();
                        return;
                    }
                    catch (Exception ex)
                    {
                        MessageBox.Show("Could not elevate installer: " + ex.Message, "Elevation Failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
                        return;
                    }
                }
                else
                {
                    return;
                }
            }

            isInstalling = true;
            btnInstall.Enabled = false;
            btnBrowse.Enabled = false;
            txtInstallDir.Enabled = false;
            chkDesktopShortcut.Enabled = false;
            chkStartMenuShortcut.Enabled = false;
            progressBar.Visible = true;

            Thread worker = new Thread(() =>
            {
                try
                {
                    InstallerCore.ExecuteInstall(
                        finalInstallPath,
                        chkDesktopShortcut.Checked,
                        chkStartMenuShortcut.Checked,
                        (status, details, progress) => SetStatus(status, details, progress)
                    );

                    this.BeginInvoke(new Action(() =>
                    {
                        progressBar.Value = 100;
                        lblStatus.Text = "Installation Completed Successfully!";
                        lblStatus.ForeColor = Color.FromArgb(0, 230, 118);
                        lblDetails.Text = "Installed to: " + finalInstallPath + "\nRequired AI models will be acquired automatically on first launch.";
                        chkLaunch.Visible = true;
                        btnInstall.Text = "Finish";
                        btnInstall.Enabled = true;
                        btnInstall.BackColor = Color.FromArgb(35, 134, 54);
                    }));
                }
                catch (Exception ex)
                {
                    this.BeginInvoke(new Action(() =>
                    {
                        lblStatus.Text = "Installation Encountered an Error";
                        lblStatus.ForeColor = Color.FromArgb(248, 81, 73);
                        lblDetails.Text = ex.Message;
                        btnInstall.Text = "Close";
                        btnInstall.Enabled = true;
                        btnInstall.BackColor = Color.FromArgb(182, 35, 36);
                    }));
                }
            });
            worker.IsBackground = true;
            worker.Start();
        }

        private void SetStatus(string status, string details, int progress)
        {
            if (this.InvokeRequired)
            {
                this.BeginInvoke(new Action(() => SetStatus(status, details, progress)));
                return;
            }

            lblStatus.Text = status;
            lblDetails.Text = details;
            if (progress >= 0 && progress <= 100)
            {
                progressBar.Value = progress;
            }
        }
    }

    public class UninstallerForm : Form
    {
        private Label lblTitle;
        private Label lblMessage;
        private Button btnUninstall;
        private Button btnCancel;
        private ProgressBar progressBar;
        private Label lblStatus;

        public UninstallerForm()
        {
            InitializeComponent();
        }

        private void InitializeComponent()
        {
            this.Text = "PRAHARI Uninstaller";
            this.Size = new Size(500, 240);
            this.StartPosition = FormStartPosition.CenterScreen;
            this.FormBorderStyle = FormBorderStyle.FixedDialog;
            this.MaximizeBox = false;
            this.BackColor = Color.FromArgb(15, 17, 23);
            this.ForeColor = Color.FromArgb(230, 237, 243);
            this.Font = new Font("Segoe UI", 9F);

            lblTitle = new Label
            {
                Text = "Uninstall PRAHARI",
                Font = new Font("Segoe UI", 12F, FontStyle.Bold),
                ForeColor = Color.FromArgb(248, 81, 73),
                Location = new Point(20, 15),
                AutoSize = true
            };
            this.Controls.Add(lblTitle);

            lblMessage = new Label
            {
                Text = "Are you sure you want to remove PRAHARI and all its components?\n\nNote: User data, logs, and downloaded models in %LOCALAPPDATA%\\PRAHARI will be preserved.",
                Location = new Point(22, 50),
                Size = new Size(440, 60),
                ForeColor = Color.FromArgb(139, 148, 158)
            };
            this.Controls.Add(lblMessage);

            progressBar = new ProgressBar
            {
                Location = new Point(24, 115),
                Size = new Size(436, 18),
                Visible = false
            };
            this.Controls.Add(progressBar);

            lblStatus = new Label
            {
                Location = new Point(24, 140),
                Size = new Size(436, 20),
                ForeColor = Color.FromArgb(0, 230, 118),
                Visible = false
            };
            this.Controls.Add(lblStatus);

            btnUninstall = new Button
            {
                Text = "Uninstall",
                Location = new Point(280, 155),
                Size = new Size(95, 28),
                FlatStyle = FlatStyle.Flat,
                BackColor = Color.FromArgb(182, 35, 36),
                ForeColor = Color.White,
                Cursor = Cursors.Hand
            };
            btnUninstall.FlatAppearance.BorderSize = 0;
            btnUninstall.Click += BtnUninstall_Click;
            this.Controls.Add(btnUninstall);

            btnCancel = new Button
            {
                Text = "Cancel",
                Location = new Point(385, 155),
                Size = new Size(75, 28),
                FlatStyle = FlatStyle.Flat,
                BackColor = Color.FromArgb(33, 38, 45),
                ForeColor = Color.White,
                Cursor = Cursors.Hand
            };
            btnCancel.FlatAppearance.BorderColor = Color.FromArgb(48, 54, 61);
            btnCancel.Click += (s, e) => Application.Exit();
            this.Controls.Add(btnCancel);
        }

        private void BtnUninstall_Click(object sender, EventArgs e)
        {
            if (btnUninstall.Text == "Close")
            {
                Application.Exit();
                return;
            }

            btnUninstall.Enabled = false;
            btnCancel.Enabled = false;
            progressBar.Visible = true;
            progressBar.Style = ProgressBarStyle.Marquee;
            lblStatus.Visible = true;
            lblStatus.Text = "Removing PRAHARI application files and shortcuts...";

            Thread worker = new Thread(() =>
            {
                try
                {
                    string installDir = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\');
                    InstallerCore.ExecuteUninstall(installDir);

                    this.BeginInvoke(new Action(() =>
                    {
                        progressBar.Visible = false;
                        lblStatus.Text = "PRAHARI has been uninstalled successfully.";
                        lblMessage.Text = "Application files and shortcuts have been removed.\nYour models and logs in %LOCALAPPDATA%\\PRAHARI were preserved.";
                        btnUninstall.Text = "Close";
                        btnUninstall.Enabled = true;
                        btnUninstall.BackColor = Color.FromArgb(35, 134, 54);
                    }));
                }
                catch (Exception ex)
                {
                    this.BeginInvoke(new Action(() =>
                    {
                        progressBar.Visible = false;
                        lblStatus.ForeColor = Color.FromArgb(248, 81, 73);
                        lblStatus.Text = "Uninstall encountered an error: " + ex.Message;
                        btnUninstall.Text = "Close";
                        btnUninstall.Enabled = true;
                    }));
                }
            });
            worker.IsBackground = true;
            worker.Start();
        }
    }
}
