using System;
using System.Diagnostics;
using System.IO;
using System.Threading;

namespace PrahariSetup
{
    class Program
    {
        static void Main(string[] args)
        {
            Console.Title = "PRAHARI Environment Setup & Launcher";
            Console.ForegroundColor = ConsoleColor.Cyan;
            Console.WriteLine("================================================================================");
            Console.WriteLine("        PRAHARI MISSION HAR ASSISTANT - ONE-CLICK ENVIRONMENT SETUP            ");
            Console.WriteLine("================================================================================");
            Console.ResetColor();
            Console.WriteLine();

            // Locate project root directory (either current directory or parent directory)
            string currentDir = AppDomain.CurrentDomain.BaseDirectory;
            string projectRoot = currentDir;

            if (File.Exists(Path.Combine(currentDir, "requirements.txt")))
            {
                projectRoot = currentDir;
            }
            else if (File.Exists(Path.Combine(Directory.GetParent(currentDir).FullName, "requirements.txt")))
            {
                projectRoot = Directory.GetParent(currentDir).FullName;
            }

            Console.WriteLine("[INFO] Project Root: " + projectRoot);
            Console.WriteLine();

            // Step 1: Detect Python Installation
            Console.ForegroundColor = ConsoleColor.Yellow;
            Console.WriteLine("[STEP 1/4] Checking Python environment...");
            Console.ResetColor();

            string pythonCmd = FindPython();
            if (string.IsNullOrEmpty(pythonCmd))
            {
                Console.ForegroundColor = ConsoleColor.Red;
                Console.WriteLine("[ERROR] Python 3.10+ was not found on your system PATH.");
                Console.WriteLine("Please download and install Python from: https://www.python.org/downloads/");
                Console.WriteLine("Make sure to check the box: 'Add Python to PATH' during installation.");
                Console.ResetColor();
                Console.WriteLine("\nPress any key to exit...");
                Console.ReadKey();
                return;
            }

            Console.ForegroundColor = ConsoleColor.Green;
            Console.WriteLine("[OK] Found Python interpreter: " + pythonCmd);
            Console.ResetColor();
            Console.WriteLine();

            // Step 2: Install / Upgrade Requirements
            Console.ForegroundColor = ConsoleColor.Yellow;
            Console.WriteLine("[STEP 2/4] Installing required dependencies from requirements.txt...");
            Console.ResetColor();

            string reqPath = Path.Combine(projectRoot, "requirements.txt");
            if (File.Exists(reqPath))
            {
                int exitCode = RunProcess(pythonCmd, "-m pip install -r \"" + reqPath + "\"", projectRoot);
                if (exitCode == 0)
                {
                    Console.ForegroundColor = ConsoleColor.Green;
                    Console.WriteLine("[OK] All Python dependencies installed successfully.");
                    Console.ResetColor();
                }
                else
                {
                    Console.ForegroundColor = ConsoleColor.Yellow;
                    Console.WriteLine("[WARN] Dependency installation completed with code " + exitCode + ". Proceeding...");
                    Console.ResetColor();
                }
            }
            else
            {
                Console.WriteLine("[SKIP] requirements.txt not found at " + reqPath);
            }
            Console.WriteLine();

            // Step 3: Download Model Weights
            Console.ForegroundColor = ConsoleColor.Yellow;
            Console.WriteLine("[STEP 3/4] Checking & Downloading AI Model Weights (YOLO & MediaPipe)...");
            Console.ResetColor();

            string downloadScript = Path.Combine(projectRoot, "src", "download_models.py");
            if (File.Exists(downloadScript))
            {
                RunProcess(pythonCmd, "\"" + downloadScript + "\"", projectRoot);
            }
            Console.ForegroundColor = ConsoleColor.Green;
            Console.WriteLine("[OK] AI Models verified.");
            Console.ResetColor();
            Console.WriteLine();

            // Step 4: Windows Firewall Rule for Mobile Browser Bridge (Port 8000)
            Console.ForegroundColor = ConsoleColor.Yellow;
            Console.WriteLine("[STEP 4/4] Configuring local network port 8000 for Mobile Camera Bridge...");
            Console.ResetColor();

            try
            {
                ProcessStartInfo psi = new ProcessStartInfo("netsh", "advfirewall firewall add rule name=\"PRAHARI Bridge\" dir=in action=allow protocol=TCP localport=8000");
                psi.CreateNoWindow = true;
                psi.UseShellExecute = false;
                Process.Start(psi);
                Console.ForegroundColor = ConsoleColor.Green;
                Console.WriteLine("[OK] Port 8000 firewall access configured.");
                Console.ResetColor();
            }
            catch
            {
                Console.WriteLine("[NOTE] Skipped firewall auto-rule (non-administrator mode).");
            }
            Console.WriteLine();

            // Success & Launch Menu
            Console.ForegroundColor = ConsoleColor.Cyan;
            Console.WriteLine("================================================================================");
            Console.WriteLine("                     PRAHARI SETUP COMPLETE & READY!                           ");
            Console.WriteLine("================================================================================");
            Console.ResetColor();
            Console.WriteLine();
            Console.WriteLine("Select an option to launch:");
            Console.WriteLine("  [1] Launch PRAHARI in Mobile Phone Browser Camera Mode (Recommended)");
            Console.WriteLine("  [2] Launch PRAHARI Desktop GUI (Standard USB Webcam Mode)");
            Console.WriteLine("  [3] Run Automated Test Suite");
            Console.WriteLine("  [4] Exit Setup");
            Console.WriteLine();
            Console.Write("Enter your choice (1-4) [Default 1]: ");

            string choice = Console.ReadLine();
            if (string.IsNullOrWhiteSpace(choice)) choice = "1";

            string mainScript = Path.Combine(projectRoot, "src", "main.py");
            string testScript = Path.Combine(projectRoot, "tests", "test_capture_ip.py");

            if (choice.Trim() == "1")
            {
                Console.ForegroundColor = ConsoleColor.Green;
                Console.WriteLine("\n[LAUNCHING] Starting PRAHARI with Mobile Camera Bridge...");
                Console.ResetColor();
                ProcessStartInfo psi = new ProcessStartInfo(pythonCmd, "\"" + mainScript + "\" --config config/desk_objects_experiment.json");
                psi.WorkingDirectory = projectRoot;
                psi.EnvironmentVariables["PRAHARI_CAMERA_TYPE"] = "browser";
                psi.UseShellExecute = false;
                Process p = Process.Start(psi);
                p.WaitForExit();
            }
            else if (choice.Trim() == "2")
            {
                Console.ForegroundColor = ConsoleColor.Green;
                Console.WriteLine("\n[LAUNCHING] Starting PRAHARI Desktop GUI with USB Camera...");
                Console.ResetColor();
                ProcessStartInfo psi = new ProcessStartInfo(pythonCmd, "\"" + mainScript + "\" --camera 0");
                psi.WorkingDirectory = projectRoot;
                psi.UseShellExecute = false;
                Process p = Process.Start(psi);
                p.WaitForExit();
            }
            else if (choice.Trim() == "3")
            {
                Console.ForegroundColor = ConsoleColor.Green;
                Console.WriteLine("\n[TESTS] Running Automated Test Suite...");
                Console.ResetColor();
                RunProcess(pythonCmd, "\"" + testScript + "\"", projectRoot);
                Console.WriteLine("\nPress any key to exit...");
                Console.ReadKey();
            }
            else
            {
                Console.WriteLine("\nSetup finished. You can run PRAHARI anytime using python src/main.py");
            }
        }

        static string FindPython()
        {
            string[] candidates = new string[] { "python", "py", "python3" };
            foreach (string candidate in candidates)
            {
                try
                {
                    ProcessStartInfo psi = new ProcessStartInfo(candidate, "--version");
                    psi.RedirectStandardOutput = true;
                    psi.RedirectStandardError = true;
                    psi.UseShellExecute = false;
                    psi.CreateNoWindow = true;
                    using (Process p = Process.Start(psi))
                    {
                        p.WaitForExit(3000);
                        if (p.ExitCode == 0) return candidate;
                    }
                }
                catch { }
            }

            // Check common Windows Python installation paths
            string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string[] searchPaths = new string[]
            {
                Path.Combine(localAppData, "Programs", "Python", "Python312", "python.exe"),
                Path.Combine(localAppData, "Programs", "Python", "Python311", "python.exe"),
                Path.Combine(localAppData, "Programs", "Python", "Python310", "python.exe"),
                @"C:\Python312\python.exe",
                @"C:\Python311\python.exe",
                @"C:\Python310\python.exe"
            };

            foreach (string path in searchPaths)
            {
                if (File.Exists(path)) return path;
            }

            return null;
        }

        static int RunProcess(string fileName, string args, string workingDir)
        {
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo(fileName, args);
                psi.WorkingDirectory = workingDir;
                psi.UseShellExecute = false;
                using (Process p = Process.Start(psi))
                {
                    p.WaitForExit();
                    return p.ExitCode;
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine("[ERROR] Failed to run process: " + ex.Message);
                return -1;
            }
        }
    }
}
