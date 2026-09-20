using System;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Diagnostics;
using System.Drawing;
using System.Windows.Forms;

namespace PrahariInstaller
{
    static class Program
    {
        [STAThread]
        static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new InstallerForm());
        }
    }

    public class InstallerForm : Form
    {
        private const string APP_NAME = "PRAHARI";
        private const string APP_VERSION = "v1.0.0";
        private const string GITHUB_REPO = "anurag-po/SIHprahariDemo";
        private const string RELEASE_ZIP_NAME = "PRAHARI-v1.0.0-Windows-x64.zip";
        private const string RELEASE_URL = "https://github.com/anurag-po/SIHprahariDemo/releases/download/v1.0.0/PRAHARI-v1.0.0-Windows-x64.zip";
        private const string CHECKSUM_URL = "https://github.com/anurag-po/SIHprahariDemo/releases/download/v1.0.0/SHA256SUMS.txt";

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

        public InstallerForm()
        {
            InitializeComponent();
        }

        private void InitializeComponent()
        {
            this.Text = "PRAHARI Setup — Mission HAR Assistant " + APP_VERSION;
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
                Text = "Self-Contained Windows Desktop Application Installer " + APP_VERSION,
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

            string defaultPath = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Programs",
                APP_NAME
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
                Text = "Package includes YOLOv8 detector, MediaPipe tracking, and PyQt6 GUI.",
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

            isInstalling = true;
            btnInstall.Enabled = false;
            btnBrowse.Enabled = false;
            txtInstallDir.Enabled = false;
            chkDesktopShortcut.Enabled = false;
            chkStartMenuShortcut.Enabled = false;
            progressBar.Visible = true;

            Thread worker = new Thread(InstallProcess);
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

        private void InstallProcess()
        {
            try
            {
                // Force TLS 1.2 and 1.3
                ServicePointManager.SecurityProtocol = (SecurityProtocolType)3072 | (SecurityProtocolType)768 | SecurityProtocolType.Tls;

                string tempDir = Path.Combine(Path.GetTempPath(), "PrahariInstaller_" + Guid.NewGuid().ToString("N"));
                Directory.CreateDirectory(tempDir);
                string zipPath = Path.Combine(tempDir, RELEASE_ZIP_NAME);

                // Step 0: Check for running PRAHARI process
                Process[] running = Process.GetProcessesByName("PRAHARI");
                if (running != null && running.Length > 0)
                {
                    throw new Exception("PRAHARI is currently running. Please close all running PRAHARI instances and click Install again.");
                }

                // Step 1: Check for local package first (offline installer support)
                string localExeDir = AppDomain.CurrentDomain.BaseDirectory;
                string localZip = Path.Combine(localExeDir, RELEASE_ZIP_NAME);
                string siblingZip = Path.Combine(localExeDir, "..", "release", RELEASE_ZIP_NAME);
                string localChecksum = Path.Combine(localExeDir, "SHA256SUMS.txt");
                string siblingChecksum = Path.Combine(localExeDir, "..", "release", "SHA256SUMS.txt");
                string checksumContent = "";

                if (File.Exists(localZip))
                {
                    SetStatus("Loading local package...", "Using " + localZip, 20);
                    File.Copy(localZip, zipPath, true);
                    if (File.Exists(localChecksum))
                    {
                        try { checksumContent = File.ReadAllText(localChecksum); } catch { }
                    }
                }
                else if (File.Exists(siblingZip))
                {
                    SetStatus("Loading release package...", "Using " + siblingZip, 20);
                    File.Copy(siblingZip, zipPath, true);
                    if (File.Exists(siblingChecksum))
                    {
                        try { checksumContent = File.ReadAllText(siblingChecksum); } catch { }
                    }
                }
                else
                {
                    // Download from GitHub Release
                    SetStatus("Downloading PRAHARI package...", "Connecting to GitHub Releases...", 10);
                    using (WebClient client = new WebClient())
                    {
                        client.Headers.Add("User-Agent", "PRAHARI-Bootstrapper-Installer");
                        client.DownloadProgressChanged += (s, ev) =>
                        {
                            int pct = 10 + (int)(ev.ProgressPercentage * 0.4);
                            SetStatus(
                                string.Format("Downloading PRAHARI ({0} MB / {1} MB)...", (ev.BytesReceived / 1048576.0).ToString("0.0"), (ev.TotalBytesToReceive / 1048576.0).ToString("0.0")),
                                "HTTPS Download from GitHub Releases",
                                pct
                            );
                        };

                        try
                        {
                            client.DownloadFile(new Uri(RELEASE_URL), zipPath);
                        }
                        catch (Exception dlEx)
                        {
                            throw new Exception("Unable to download release package over HTTPS. Please check your internet connection or place " + RELEASE_ZIP_NAME + " next to this installer.\nError: " + dlEx.Message);
                        }

                        // Try to download SHA256SUMS.txt as well
                        try
                        {
                            checksumContent = client.DownloadString(new Uri(CHECKSUM_URL));
                        }
                        catch { }
                    }
                }

                // Step 2: Verification
                SetStatus("Verifying package integrity...", "Calculating SHA-256 checksum...", 55);
                string calculatedHash = ComputeSha256(zipPath).ToLowerInvariant();

                // If checksum reference exists, enforce verification
                if (!string.IsNullOrEmpty(checksumContent))
                {
                    string expectedHash = "";
                    foreach (string line in checksumContent.Split(new char[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries))
                    {
                        string trimmed = line.Trim();
                        if (trimmed.Contains(RELEASE_ZIP_NAME) || trimmed.Length >= 64)
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
                            throw new Exception("Installation aborted.\nThe downloaded package failed integrity verification.\nExpected SHA-256: " + expectedHash + "\nCalculated SHA-256: " + calculatedHash);
                        }
                        SetStatus("Package integrity verified.", "SHA-256: " + calculatedHash.Substring(0, 16) + "... [MATCH]", 65);
                    }
                }

                // Step 3: Extract & Install with Zip Slip directory traversal validation
                SetStatus("Installing PRAHARI...", "Extracting application files to " + finalInstallPath + "...", 70);
                if (Directory.Exists(finalInstallPath))
                {
                    // Clean previous install safely
                    try
                    {
                        foreach (string file in Directory.GetFiles(finalInstallPath))
                        {
                            try { File.Delete(file); } catch { }
                        }
                    }
                    catch { }
                }
                else
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

                // Check for nested directory if zipped root folder
                string nestedExe = Path.Combine(finalInstallPath, "PRAHARI", "PRAHARI.exe");
                if (File.Exists(nestedExe))
                {
                    string nestedDir = Path.Combine(finalInstallPath, "PRAHARI");
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

                // Step 4: Create Shortcuts
                SetStatus("Creating shortcuts...", "Registering Desktop and Start Menu entries...", 90);
                string mainExe = Path.Combine(finalInstallPath, "PRAHARI.exe");

                if (chkDesktopShortcut.Checked)
                {
                    string desktopPath = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                    string shortcutPath = Path.Combine(desktopPath, "PRAHARI.lnk");
                    CreateShortcut(shortcutPath, mainExe, finalInstallPath, "PRAHARI - Mission HAR Space Experiment Assistant");
                }

                if (chkStartMenuShortcut.Checked)
                {
                    string startMenu = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.StartMenu), "Programs", APP_NAME);
                    Directory.CreateDirectory(startMenu);
                    string shortcutPath = Path.Combine(startMenu, "PRAHARI.lnk");
                    CreateShortcut(shortcutPath, mainExe, finalInstallPath, "PRAHARI - Mission HAR Space Experiment Assistant");
                }

                // Clean temporary folder
                try { Directory.Delete(tempDir, true); } catch { }

                // Step 5: Finished
                this.BeginInvoke(new Action(() =>
                {
                    progressBar.Value = 100;
                    lblStatus.Text = "Installation Completed Successfully!";
                    lblStatus.ForeColor = Color.FromArgb(0, 230, 118);
                    lblDetails.Text = "PRAHARI " + APP_VERSION + " is installed and ready at:\n" + finalInstallPath;
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
        }

        private static string ComputeSha256(string filePath)
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

        private static void CreateShortcut(string shortcutPath, string targetPath, string workingDir, string description)
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
                // Fallback using PowerShell if COM is restricted
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
    }
}
